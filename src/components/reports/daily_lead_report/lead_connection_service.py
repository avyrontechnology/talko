from datetime import datetime
from typing import Any, Dict, List, Set
from zoneinfo import ZoneInfo

from src.components.cdr.models import CDR
from src.components.integrations.console.maglo_client import MagloClient
from src.core.doc_db import DocDatabaseSessionManager
from src.loggers.holler_service_logger import HollerServiceLogger


class LeadConnectionReportService:
    def __init__(
        self,
        maglo_client: MagloClient,
        db_manager: DocDatabaseSessionManager,
        logger: HollerServiceLogger,
    ):
        self.maglo_client = maglo_client
        self.db_manager = db_manager
        self.logger = logger

        self.logger.debug("LeadConnectionReportService initialized")

    async def generate_daily_report(self, api_key: str) -> List[Dict[str, Any]]:
        self.logger.info("Generating daily lead connection report")

        data = await self.maglo_client.get_leads_created_today(api_key)
        self.logger.debug("Maglo response received")
        self.logger.debug(f"Maglo response data: {data}")

        boards = data.get("service_boards", [])
        self.logger.debug(f"Total boards received: {len(boards)}")

        if not boards:
            self.logger.warning("No service boards found in Maglo response")
            return []

        agent_summary = self._build_agent_summary(boards)
        self.logger.debug(f"Agents aggregated: {len(agent_summary)}")

        if not agent_summary:
            self.logger.warning("Agent summary empty after processing boards")
            return []

        start_ms, end_ms = self._get_today_range_ms()
        self.logger.debug(f"Fetching connected leads between {start_ms} and {end_ms}")

        connected_leads = await self._get_connected_lead_ids(start_ms, end_ms)

        self.logger.debug(f"Connected lead IDs fetched: {connected_leads}")
        self.logger.info(
            "Agent summary built successfully: processing connections: data: {}".format(
                agent_summary
            )
        )

        rows = self._build_report_rows(agent_summary, connected_leads)
        self.logger.info(f"Final report rows generated: {len(rows)}")

        return rows

    def _build_agent_summary(self, boards: List[Dict]) -> Dict[str, Dict]:
        agent_data: Dict[str, Dict] = {}

        for board in boards:
            service_board_id = board.get("service_board_id")
            agents = board.get("agents", [])

            for agent_block in agents:
                self._process_single_agent(agent_block, service_board_id, agent_data)

        return agent_data

    def _process_single_agent(
        self,
        agent_block: Dict,
        service_board_id: int,
        agent_data: Dict[str, Dict],
    ) -> None:
        agent_id = agent_block.get("agent_id")
        if agent_id is None:
            return

        key = f"{service_board_id}_{agent_id}"

        if key not in agent_data:
            agent_data[key] = {
                "service_board_id": service_board_id,
                "agent_id": agent_id,
                "agent_name": agent_block.get("agent_name", f"Agent_{agent_id}"),
                "total_leads": 0,
                "lead_ids": set(),
            }

        entry = agent_data[key]
        count = agent_block.get("count", 0)
        entry["total_leads"] += count

        self._add_lead_ids_from_block(agent_block, entry["lead_ids"])

    def _add_lead_ids_from_block(self, agent_block: Dict, lead_ids: Set[int]) -> None:
        leads = agent_block.get("leads", [])
        self.logger.debug(
            f"Processing {len(leads)} lead entries for agent {agent_block.get('agent_name')}"
        )
        self.logger.debug(f"Lead entries: {leads}")

        added = 0
        for lead in leads:
            self.logger.debug(f"Processing lead object: {lead}")
            identifier = self._safe_extract_lead_identifier(lead)
            if identifier is not None:
                lead_ids.add(identifier)
                added += 1

        self.logger.debug(f"Added {added} lead identifiers from block")

    @staticmethod
    def _safe_extract_lead_identifier(lead: Dict) -> int | None:
        # Order is important: lead_request_id comes FIRST
        for key in ("lead_request_id", "lead_id"):
            raw = lead.get(key)
            if raw is not None:
                try:
                    return int(raw)
                except (ValueError, TypeError):
                    continue
        return None

    async def _get_connected_lead_ids(self, start_ms: int, end_ms: int) -> Set[int]:
        self.logger.info("Fetching connected lead IDs from CDR")

        pipeline = [
            {
                "$match": {
                    "created_at": {"$gte": start_ms, "$lte": end_ms},
                    "lead_id": {"$exists": True, "$ne": None},
                }
            },
            {"$group": {"_id": "$lead_id"}},
        ]

        self.logger.debug(f"Aggregation pipeline: {pipeline}")

        result: Set[int] = set()

        async with self.db_manager.collection(CDR.CollectionName.CDR) as collection:
            self.logger.debug("Mongo aggregation started")

            async for doc in collection.aggregate(pipeline):
                lid = doc.get("_id")
                if lid is not None:
                    try:
                        result.add(int(lid))
                    except (ValueError, TypeError):
                        self.logger.warning(f"Invalid lead_id in CDR: {lid}")

        self.logger.debug("Mongo aggregation completed")
        self.logger.debug(f"Connected lead IDs: {result}")

        self.logger.info(f"Connected leads found today: {len(result)}")
        return result

    def _build_report_rows(
        self,
        agent_summary: Dict[str, Dict],
        connected_leads: Set[int],
    ) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []

        for entry in agent_summary.values():
            self.logger.debug(f"Processing agent entry: {entry}")
            total = entry["total_leads"]
            self.logger.debug(f"Total leads for agent {entry['agent_id']}: {total}")
            connected = len(entry["lead_ids"] & connected_leads)
            self.logger.debug(
                f"Connected leads for agent {entry['agent_id']}: {connected}"
            )

            rows.append(
                {
                    "service_board_id": entry["service_board_id"],
                    "agent_id": entry["agent_id"],
                    "agent_name": entry["agent_name"],
                    "total_leads": total,
                    "connected": connected,
                    "not_connected": total - connected,
                }
            )
            self.logger.debug(f"Report row added for agent {entry['agent_id']}")
            self.logger.info("Report row data: {}".format(rows[-1]))

        rows.sort(key=lambda x: x["total_leads"], reverse=True)

        self.logger.info("Report rows built and sorted successfully")
        self.logger.debug(f"Final report rows: {rows}")
        return rows

    def _get_today_range_ms(self) -> tuple[int, int]:
        now = datetime.now(ZoneInfo("Asia/Kolkata"))
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=23, minute=59, second=59, microsecond=999999)

        self.logger.debug(
            f"Today's time range (ms): {start.timestamp()*1000} - {end.timestamp()*1000}"
        )

        return int(start.timestamp() * 1000), int(end.timestamp() * 1000)
