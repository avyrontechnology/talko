from typing import Any, Dict, Optional

import aiohttp

from src.components.integrations.console.console_constants import TalkoConsoleApiConstants
from src.loggers.talko_service_logger import TalkoServiceLogger


class TalkoConsoleClient:
    def __init__(
        self,
        logger: TalkoServiceLogger,
    ):
        self.logger: TalkoServiceLogger = logger
        self.session: aiohttp.ClientSession = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(
                total=TalkoConsoleApiConstants.REQUEST_TIMEOUT_SECONDS
            )
        )
        self.api_key: Optional[str] = TalkoConsoleApiConstants.CONSOLE_API_KEY

        if not self.api_key:
            self.logger.warning("Console API key is missing — agent lookup will fail")

    async def _read_json_response(self, resp: aiohttp.ClientResponse) -> Dict[str, Any]:
        try:
            data = await resp.json()
            if isinstance(data, dict):
                return data

            self.logger.warning(
                "Console returned non-dict JSON response: {}".format(type(data))
            )
            return {}
        except Exception:
            text: str = await resp.text()
            self.logger.warning(
                "Console returned non-JSON response: {}".format(text[:200])
            )
            return {}

    async def get_agent_by_ivr_phone(
        self,
        partner_id: int,
        ivr_phone: str,
    ) -> Dict[str, Any]:
        """
        GET /console-service/v1/{partner_id}/user/{ivr_phone}/get_user_details_by_ivr
        Returns the inner 'data' object or {} on failure/not found.
        """
        if not ivr_phone or not ivr_phone.strip():
            self.logger.warning("Empty IVR phone — skipping agent lookup")
            return {}

        if not self.api_key:
            self.logger.error("Console API key missing — cannot fetch agent")
            return {}

        url: str = TalkoConsoleApiConstants.get_agent_by_ivr_phone_url(
            partner_id=partner_id,
            ivr_phone=ivr_phone,
        )

        headers: Dict[str, str] = {
            "accept": "application/json",
            TalkoConsoleApiConstants.API_KEY_HEADER: self.api_key,
        }

        self.logger.debug(
            "Fetching agent by IVR phone ending {} for partner {}".format(
                ivr_phone[-6:], partner_id
            )
        )

        try:
            async with self.session.get(url, headers=headers) as resp:
                self.logger.debug(
                    "Console get_agent_by_ivr_phone status: {}".format(resp.status)
                )

                if resp.status != 200:
                    text: str = await resp.text()
                    self.logger.warning(
                        "Console agent lookup failed {}: {}".format(
                            resp.status, text[:150]
                        )
                    )
                    return {}

                response: Dict[str, Any] = await self._read_json_response(resp)
                if not response:
                    return {}

                if (
                    response.get(TalkoConsoleApiConstants.FIELD_STATUS)
                    == TalkoConsoleApiConstants.STATUS_SUCCESS
                    and isinstance(response.get(TalkoConsoleApiConstants.FIELD_DATA), dict)
                ):
                    agent_data: Dict[str, Any] = response[
                        TalkoConsoleApiConstants.FIELD_DATA
                    ]
                    self.logger.debug(
                        "Agent found: id={}, name={}".format(
                            agent_data.get(TalkoConsoleApiConstants.FIELD_AGENT_ID),
                            agent_data.get(TalkoConsoleApiConstants.FIELD_AGENT_NAME),
                        )
                    )
                    return agent_data

                self.logger.info(
                    "Console returned non-success: {}".format(
                        response.get(TalkoConsoleApiConstants.FIELD_MESSAGE, "no message")
                    )
                )
                return {}

        except Exception as e:
            self.logger.exception(
                "Exception during console agent lookup for phone {}: {}".format(
                    ivr_phone[-6:], str(e)
                )
            )
            return {}

    async def close(self) -> None:
        """Close session when app shuts down."""
        if not self.session.closed:
            await self.session.close()
            self.logger.debug("TalkoConsoleClient session closed")
