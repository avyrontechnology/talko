import os
from typing import Dict

from src.core.environment import TalkoENV


class TalkoMagloApiConstants:
    """
    Centralized constants for Maglo API integration.
    All values can be overridden via environment variables.
    Use these in TalkoMagloClient or any service that calls Maglo APIs.
    """

    # Base URL – different environments
    MAGLO_BASE_URL: str = TalkoENV.MAGLO_BASE_URL or (
        "https://int-maglo-service.makunaiglobal.ai/maglo-service"  # fallback if not set in TalkoENV
    )
    MAGLO_API_TOKEN: str = ""

    # Endpoints (relative paths – do NOT include base URL)
    GET_AGENT_DETAILS_PATH = "/v1/get_agent_details"
    UPSERT_IVR_LEADS_PATH = "/v1/ivr-leads"
    LEADS_CREATED_TODAY_PATH = "/v1/leads-created-today"
    REASSIGN_LEAD_BY_PHONE_PATH = "/v1/leads/reassign-by-phone"

    # Full computed URLs (use these in your client)
    @classmethod
    def get_agent_details_url(cls) -> str:
        """Returns full URL for get_agent_details endpoint"""
        base = cls.MAGLO_BASE_URL.rstrip("/")
        return "{}{}".format(base, cls.GET_AGENT_DETAILS_PATH)

    @classmethod
    def upsert_ivr_leads_url(cls) -> str:
        """Full URL for IVR leads upsert/creation endpoint"""
        return "{}{}".format(cls.MAGLO_BASE_URL.rstrip("/"), cls.UPSERT_IVR_LEADS_PATH)

    @classmethod
    def leads_created_today_url(cls) -> str:
        return f"{cls.MAGLO_BASE_URL.rstrip('/')}{cls.LEADS_CREATED_TODAY_PATH}"

    @classmethod
    def reassign_lead_by_phone_url(cls) -> str:
        """Full URL for the lead reassignment endpoint"""
        return "{}{}".format(
            cls.MAGLO_BASE_URL.rstrip("/"), cls.REASSIGN_LEAD_BY_PHONE_PATH
        )

    # Default request settings
    REQUEST_TIMEOUT_SECONDS: int = 10  # seconds

    DEFAULT_HEADERS: Dict[str, str] = {
        "accept": "application/json",
        "Content-Type": "application/json",
    }

    # Query parameter defaults / common values
    API_KEY_FIELD = "api_key"
    DEFAULT_SERVICE_BOARD_ID_PARAM = "service_board_id"
    DEFAULT_AGENT_ID_PARAM = "agent_id"
    LEAD_PAYLOAD_PHONE_NUMBER = "phone_number"
    LEAD_PAYLOAD_PARTNER_ID = "partner_id"
    LEAD_PAYLOAD_PERFORMED_BY = "performed_by"

    # Response field names (to avoid magic strings)
    FIELD_INTERNET_CALLING_ENABLE = "internet_calling_enable"
    FIELD_EXTENSION = "extension"
    FIELD_AGENT_ID = "id"
    FIELD_LEAD_ID = "id"
    FIELD_LEAD_REQUEST_ID = "lead_request_id"
    FIELD_AGENT_NAME = "name"
    FIELD_AGENT_NUMBER = "number"
    LEAD_RESPONSE_ASSIGNED_TO = "assigned_to"
    LEAD_RESPONSE_PHONE_NUMBER = "phone_number"

    # Logging / debug helpers
    @classmethod
    def log_current_config(cls):
        """Call once on startup to log Maglo config"""
        print("[Maglo Config] Base URL: {}".format(cls.MAGLO_BASE_URL))
        print(
            "[Maglo Config] Agent Details URL: {}".format(cls.get_agent_details_url())
        )
        print(
            "[Maglo Config] IVR Leads Upsert URL: {}".format(cls.upsert_ivr_leads_url())
        )
        print("[Maglo Config] Timeout: {}s".format(cls.REQUEST_TIMEOUT_SECONDS))
