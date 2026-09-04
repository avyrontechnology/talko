"""
One-time backfill for TalkoCDR rows created before entity_type/entity_id/entity_name
existed (MGL-8214) or where the inbound lead-resolution flow never ran.

For every TalkoCDR with action="inbound" and entity_type=None:
  - if lead_id is present, sets entity_type="Lead", entity_id=lead_id, entity_name=lead_name.
  - otherwise, sets entity_type="Lead" only (entity_id/entity_name stay None), matching
    the new default applied to newly-created inbound CDRs with no resolvable lead.

Usage:
    python -m src.scripts.backfill_inbound_entity_type          # dry run, logs counts only
    python -m src.scripts.backfill_inbound_entity_type --apply  # writes the updates
"""

import argparse
import asyncio

from src.components.cdr.constants import TalkoEntityType
from src.components.cdr.models import TalkoCDR
from src.core.doc_db import TalkoDocDatabaseSessionManager
from src.loggers.talko_service_logger import TalkoServiceLogger


async def backfill(apply: bool) -> None:
    logger = TalkoServiceLogger()
    db_manager = TalkoDocDatabaseSessionManager(logger)

    async with db_manager.collection(TalkoCDR.CollectionName.TalkoCDR) as collection:
        query = {"action": "inbound", "entity_type": None}
        total = await collection.count_documents(query)
        with_lead = await collection.count_documents({**query, "lead_id": {"$ne": None}})
        logger.info(
            "Found {} inbound CDRs with entity_type=None ({} have lead_id set)".format(
                total, with_lead
            )
        )

        if not apply:
            logger.info("Dry run only, no writes made. Re-run with --apply to update.")
            return

        updated_with_lead = 0
        updated_without_lead = 0
        cursor = collection.find(query, {"_id": 1, "lead_id": 1, "lead_name": 1})
        async for doc in cursor:
            lead_id = doc.get("lead_id")
            if lead_id is not None:
                update = {
                    "entity_type": TalkoEntityType.LEAD.value,
                    "entity_id": lead_id,
                    "entity_name": doc.get("lead_name"),
                }
                updated_with_lead += 1
            else:
                update = {"entity_type": TalkoEntityType.LEAD.value}
                updated_without_lead += 1
            await collection.update_one({"_id": doc["_id"]}, {"$set": update})

        logger.info(
            "Backfilled entity_type/entity_id/entity_name from lead_id on {} CDRs".format(
                updated_with_lead
            )
        )
        logger.info(
            "Defaulted entity_type=Lead (no lead_id) on {} CDRs".format(
                updated_without_lead
            )
        )

    await db_manager.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Actually write updates (default: dry run)"
    )
    args = parser.parse_args()
    asyncio.run(backfill(args.apply))
