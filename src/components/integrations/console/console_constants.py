import os

from src.core.environment import TalkoENV


class TalkoConsoleApiConstants:
    """
    Constants for Console Service API (agent lookup by IVR phone)
    """

    CONSOLE_BASE_URL: str = (
        TalkoENV.CONSOLE_SERVICE_BASE_URL or "http://localhost:8001"
    ).rstrip("/")

    CONSOLE_API_KEY: str = TalkoENV.CONSOLE_API_KEY or os.getenv("CONSOLE_API_KEY", "")

    REQUEST_TIMEOUT_SECONDS: int = 10

    GET_AGENT_BY_IVR_PHONE_PATH_TEMPLATE = (
        "/console-service/v1/{partner_id}/user/{ivr_phone}/get_user_details_by_ivr"
    )

    API_KEY_HEADER = "x-api-key"

    FIELD_STATUS = "status"
    FIELD_MESSAGE = "message"
    FIELD_DATA = "data"

    STATUS_SUCCESS = "success"

    FIELD_AGENT_ID = "id"
    FIELD_AGENT_NAME = "name"
    FIELD_AGENT_PHONE = "phone_number"
    FIELD_AGENT_EMAIL = "email"

    @classmethod
    def get_agent_by_ivr_phone_url(cls, partner_id: int, ivr_phone: str) -> str:
        """
        Builds full URL with path parameters.
        Keep normalized phone as-is because API may expect +91-prefixed IVR phone.
        """
        path = cls.GET_AGENT_BY_IVR_PHONE_PATH_TEMPLATE.format(
            partner_id=partner_id,
            ivr_phone=ivr_phone,
        )
        return "{}{}".format(cls.CONSOLE_BASE_URL, path)
