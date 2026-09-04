import csv
import io
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from src.components.integrations.console.maglo_client import MagloClient
from src.components.reports.daily_lead_report.lead_connection_service import (
    LeadConnectionReportService,
)
from src.core.doc_db import DocDatabaseSessionManager
from src.loggers.holler_service_logger import HollerServiceLogger

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/daily-lead-connection-csv")
async def daily_lead_connection_csv(api_key: str = Query(...)):
    logger = HollerServiceLogger()
    logger.info("Daily lead connection CSV request received")

    db = DocDatabaseSessionManager(logger=logger)
    maglo = MagloClient(logger=logger)
    service = LeadConnectionReportService(maglo, db, logger)

    try:
        logger.debug("Starting daily lead connection report generation")
        records = await service.generate_daily_report(api_key)

        logger.info(f"Records generated: {len(records)}")

        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "service_board_id",
                "agent_id",
                "agent_name",
                "total_leads",
                "connected",
                "not_connected",
            ],
        )
        writer.writeheader()

        if records:
            writer.writerows(records)
        else:
            logger.warning("No records found, returning empty CSV with headers")

        # 2. Convert string buffer to bytes
        csv_content = output.getvalue()
        output.close()
        byte_io = io.BytesIO(csv_content.encode("utf-8"))  # Standard encoding for CSV

        filename = f"lead_connection_{datetime.now().strftime('%Y-%m-%d')}.csv"

        # 3. Return StreamingResponse with correct headers
        return StreamingResponse(
            byte_io,
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Type": "text/csv",
            },
        )

    except Exception as e:
        logger.exception("Error while generating daily lead connection CSV")
        raise HTTPException(status_code=500, detail=str(e))
