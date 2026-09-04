from typing import Any, Dict, Optional

import aiohttp

from src.components.integrations.console.maglo_constants import TalkoMagloApiConstants
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoMagloClient:
    """
    Simple client for Maglo APIs.
    """

    def __init__(
        self,
        logger: TalkoServiceLogger,
    ):
        self.logger: TalkoServiceLogger = logger
        self.session: aiohttp.ClientSession = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(
                total=TalkoMagloApiConstants.REQUEST_TIMEOUT_SECONDS
            )
        )
        self.base_url: str = TalkoMagloApiConstants.MAGLO_BASE_URL.rstrip("/")
        self.headers: Dict[str, str] = TalkoMagloApiConstants.DEFAULT_HEADERS.copy()

    async def get_agent_details(
        self,
        agent_id: int,
        service_board_id: int,
    ) -> Dict[str, Any]:
        """
        Fetch agent details from Maglo.
        Returns the JSON response.
        Raises exception only on critical failure.
        """
        self.logger.debug(
            "Preparing to fetch Maglo agent details for agent_id={}, board={}".format(
                agent_id, service_board_id
            )
        )
        url: str = TalkoMagloApiConstants.get_agent_details_url()
        params: Dict[str, str] = {
            "agent_id": str(agent_id),
            "service_board_id": str(service_board_id),
        }

        self.logger.debug("Maglo URL: {} with params: {}".format(url, params))

        self.logger.info(
            "Fetching Maglo agent details - agent_id={}, board={}".format(
                agent_id, service_board_id
            )
        )

        try:
            async with self.session.get(
                url, params=params, headers=self.headers
            ) as resp:
                self.logger.debug("Maglo response status: {}".format(resp.status))
                if resp.status != 200:
                    error_text: str = await resp.text()
                    self.logger.error(
                        "Maglo returned {}: {}".format(resp.status, error_text)
                    )
                    raise ValueError(
                        "Maglo error {}: {}".format(resp.status, error_text)
                    )
                data: Dict[str, Any] = await resp.json()
                self.logger.debug(
                    "Maglo response for agent {}: {}".format(agent_id, data)
                )
                return data

        except Exception as e:
            self.logger.error(
                "Failed to fetch from Maglo for agent {}: {}".format(agent_id, str(e))
            )
            raise

    async def upsert_ivr_lead(
        self,
        partner_id: int,
        service_board_id: int,
        phone_number: str,
    ) -> Dict[str, Any]:
        """
        Calls Maglo IVR Leads upsert API (PATCH /v1/ivr-leads).
        """
        url: str = TalkoMagloApiConstants.upsert_ivr_leads_url()
        payload: Dict[str, Any] = {
            TalkoMagloApiConstants.LEAD_PAYLOAD_PARTNER_ID: partner_id,
            TalkoMagloApiConstants.DEFAULT_SERVICE_BOARD_ID_PARAM: service_board_id,
            TalkoMagloApiConstants.LEAD_PAYLOAD_PHONE_NUMBER: phone_number,
        }

        self.logger.info("Upserting IVR lead: {}".format(payload))

        try:
            async with self.session.patch(
                url,
                json=payload,
                headers=self.headers,
            ) as resp:
                if resp.status != 200:
                    error_text: str = await resp.text()
                    raise ValueError(
                        "Maglo IVR lead API error {}: {}".format(
                            resp.status, error_text
                        )
                    )

                data: Dict[str, Any] = await resp.json()
                self.logger.debug("IVR lead upsert response: {}".format(data))
                inner_data: Dict[str, Any] = data.get("data", {})
                return inner_data  # return inner "data" object

        except Exception as e:
            self.logger.error("Failed to upsert IVR lead: {}".format(str(e)))
            raise

    async def reassign_lead_by_phone(
        self,
        phone_number: str,
        partner_id: int,
        service_board_id: int,
        agent_id: int,
    ) -> Dict[str, Any]:
        """
        Calls Maglo lead reassignment API (PATCH /v1/leads/reassign-by-phone)
        to hand ownership of a lead to a new agent.
        """
        url: str = TalkoMagloApiConstants.reassign_lead_by_phone_url()
        payload: Dict[str, Any] = {
            TalkoMagloApiConstants.LEAD_PAYLOAD_PHONE_NUMBER: phone_number,
            TalkoMagloApiConstants.LEAD_PAYLOAD_PARTNER_ID: partner_id,
            TalkoMagloApiConstants.DEFAULT_SERVICE_BOARD_ID_PARAM: service_board_id,
            TalkoMagloApiConstants.DEFAULT_AGENT_ID_PARAM: agent_id,
            # performed_by is the new owner itself — the reassignment is
            # system-driven (no human/admin actor), so the new agent is
            # recorded as having performed it.
            TalkoMagloApiConstants.LEAD_PAYLOAD_PERFORMED_BY: agent_id,
        }

        self.logger.info("Reassigning lead via Maglo: {}".format(payload))

        try:
            async with self.session.patch(
                url,
                json=payload,
                headers=self.headers,
            ) as resp:
                if resp.status != 200:
                    error_text: str = await resp.text()
                    raise ValueError(
                        "Maglo lead reassignment API error {}: {}".format(
                            resp.status, error_text
                        )
                    )

                data: Dict[str, Any] = await resp.json()
                self.logger.debug("Lead reassignment response: {}".format(data))
                inner_data: Dict[str, Any] = data.get("data", {})
                return inner_data  # return inner "data" object

        except Exception as e:
            self.logger.error("Failed to reassign lead via Maglo: {}".format(str(e)))
            raise

    async def get_leads_created_today(
        self,
        api_key: str,
    ) -> Dict[str, Any]:
        """
        Fetch leads created today via POST /v1/leads-created-today
        Expects body: {"api_key": "..."}
        Returns the 'data' part of the response (current_date + service_boards)
        """
        url: str = TalkoMagloApiConstants.leads_created_today_url()
        payload: Dict[str, str] = {
            TalkoMagloApiConstants.API_KEY_FIELD: api_key,
        }

        self.logger.info("Fetching leads created today")

        try:
            async with self.session.post(
                url, json=payload, headers=self.headers
            ) as resp:
                if resp.status != 200:
                    error_text: str = await resp.text()
                    self.logger.error(
                        "Maglo leads-today failed {}: {}".format(
                            resp.status, error_text
                        )
                    )
                    raise ValueError(
                        "Maglo returned {}: {}".format(resp.status, error_text)
                    )

                full_response: Dict[str, Any] = await resp.json()

                if full_response.get("status") != "success":
                    err_msg: str = full_response.get("message", "Unknown error")
                    self.logger.error(
                        "Maglo leads-today non-success: {}".format(err_msg)
                    )
                    raise ValueError("Maglo API error: {}".format(err_msg))

                data: Dict[str, Any] = full_response.get("data", {})
                self.logger.debug(
                    "Leads created today fetched - {} boards".format(
                        len(data.get("service_boards", []))
                    )
                )
                return data

        except Exception as e:
            self.logger.error("Failed to fetch leads created today: {}".format(str(e)))
            raise

    async def close(self) -> None:
        """Close session when app shuts down (optional)."""
        if not self.session.closed:
            await self.session.close()
            self.logger.debug("TalkoMagloClient session closed")
