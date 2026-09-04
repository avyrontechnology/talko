import asyncio
from typing import Any, Dict, List, Optional

import httpx

from src.components.call_management.handlers.base_handler import TalkoVendorCallHandler
from src.components.call_management.messages import (
    AGENT_NUMBER_IS_REQUIRED,
    HANGUP_URL_HANDLER_NOT_CONFIGURED,
    INVALID_PARAMETER,
    TRANSFER_URL_HANDLER_NOT_CONFIGURED,
    UNEXPECTED_API_RESPONSE,
)
from src.utils.phone_number_utils import normalize_phone_number


class TalkoTataTeleCallHandler(TalkoVendorCallHandler):
    """
    Handler for making calls via Tata Tele API.
    Supports both normal C2C (human agent) and AI Bridge (callback_url) modes.
    """

    async def make_call(
        self,
        to_number: str,
        from_number: str,
        call_url: Optional[str] = None,
        agent_number: Optional[str] = None,
        enable_ai_bridge: bool = False,  # ← NEW
    ) -> dict:
        """
        Make a call using Tata Tele's click-to-call API.

        Two modes:
        - Normal C2C (enable_ai_bridge=False): dials agent_number first,
          then connects to customer. agent_number is required.
        - AI Bridge (enable_ai_bridge=True): dials customer directly,
          Tata connects audio to callback_url WebSocket. No agent_number needed.

        Args:
            to_number: Number to be called.
            from_number: Caller ID shown.
            call_url: Not used for Tata Tele but accepted for interface compatibility.
            agent_number: Number of the agent to connect.

        Returns:
            dict: API response from Tata Tele.

        Raises:
            ValueError: If agent_number missing in normal mode, or API call fails.
        """
        try:
            self.logger.info(
                "{} call handler started. to={} from={} agent={} ai_bridge={}".format(
                    self.vendor_type,
                    to_number,
                    from_number,
                    agent_number,
                    enable_ai_bridge,
                )
            )

            endpoint: str = self.config.get("endpoint")
            auth_credentials: dict = self.config.get("auth_credentials", {})

            self.logger.debug(
                "{} endpoint={} auth={}".format(
                    self.vendor_type, endpoint, auth_credentials
                )
            )

            if enable_ai_bridge:
                # Use new vendor_config field
                c2c_handler: dict = self.vendor_config.get(
                    "c2c_support_url_handler", {}
                )
                if not c2c_handler:
                    raise ValueError(
                        "c2c_support_url_handler not configured in vendor config"
                    )

                endpoint: str = c2c_handler["endpoint"]
                api_key: str = c2c_handler["api_key"]

                payload: dict = c2c_handler["payload_template"].copy()
                payload.update(
                    {
                        "api_key": api_key,
                        "customer_number": to_number,
                        "caller_id": from_number,
                        "async": 1,
                        # "get_call_id": 1,
                    }
                )

                headers: dict = c2c_handler.get("headers", {})
                self.logger.info(
                    "{} AI bridge mode — using c2c_support endpoint".format(
                        self.vendor_type
                    )
                )
            else:
                # Normal C2C mode — unchanged behaviour
                if not agent_number:
                    self.logger.error(AGENT_NUMBER_IS_REQUIRED)
                    raise ValueError(AGENT_NUMBER_IS_REQUIRED)

                payload: dict = {
                    "agent_number": agent_number,
                    "destination_number": to_number,
                    "caller_id": from_number,
                    "async": 1,
                    "get_call_id": 1,
                }

            self.logger.debug("{} payload={}".format(self.vendor_type, payload))

            headers: dict = {
                "Content-Type": "application/json",
                "Authorization": auth_credentials.get("token"),
            }

            async with httpx.AsyncClient() as client:
                self.logger.info(
                    "Making {} API call to {}".format(self.vendor_type, endpoint)
                )
                response = await client.post(endpoint, json=payload, headers=headers)
                self.logger.debug("{} response={}".format(self.vendor_type, response))
                if response.status_code == 200:
                    json_data = response.json()
                    self.logger.info(
                        "{} API call successful: {}".format(self.vendor_type, json_data)
                    )
                    return json_data
                elif response.status_code == 400:
                    error_data = response.json()
                    error_message = error_data.get("message")
                    self.logger.error(
                        "Invalid parameters in {} API call: {}".format(
                            self.vendor_type, error_message
                        )
                    )
                    raise ValueError(INVALID_PARAMETER.format(error_message))
                elif response.status_code != 200:
                    self.logger.error(
                        "Unexpected {} API response: {} - {}".format(
                            self.vendor_type, response.status_code, response.json()
                        )
                    )
                    raise ValueError(
                        UNEXPECTED_API_RESPONSE.format(response.status_code)
                    )
        except Exception as e:
            self.logger.error(
                "Failed to make {} API call: {}".format(self.vendor_type, str(e))
            )
            raise ValueError("{} API call failed: {}".format(self.vendor_type, str(e)))

    async def hangup_call(self, call_id: str) -> dict:
        """
        Hang up an ongoing call via Tata Tele's hangup API.

        Args:
            call_id: Tata Tele's call_id for the call to hang up.

        Returns:
            dict: API response from Tata Tele ({"Success": bool, "Message": str}).

        Raises:
            ValueError: If hangup_url_handler is not configured, or the API call fails.
        """
        try:
            self.logger.info(
                "{} hangup handler started. call_id={}".format(
                    self.vendor_type, call_id
                )
            )

            hangup_config: dict = self.vendor_config.get("hangup_url_handler", {})
            if not hangup_config:
                raise ValueError(HANGUP_URL_HANDLER_NOT_CONFIGURED)

            endpoint: str = hangup_config["endpoint"]
            auth_credentials: dict = hangup_config.get("auth_credentials", {})

            headers: dict = {
                **hangup_config.get("headers", {}),
                "Authorization": auth_credentials.get("token"),
            }
            payload: dict = {"call_id": call_id}

            self.logger.debug(
                "{} hangup endpoint={} payload={}".format(
                    self.vendor_type, endpoint, payload
                )
            )

            async with httpx.AsyncClient() as client:
                self.logger.info(
                    "Making {} hangup API call to {}".format(self.vendor_type, endpoint)
                )
                response = await client.post(endpoint, json=payload, headers=headers)
                self.logger.debug(
                    "{} hangup response={}".format(self.vendor_type, response)
                )
                if response.status_code == 200:
                    json_data = response.json()
                    self.logger.info(
                        "{} hangup API call successful: {}".format(
                            self.vendor_type, json_data
                        )
                    )
                    return json_data
                elif response.status_code == 400:
                    error_data = response.json()
                    error_message = error_data.get("message") or error_data.get(
                        "Message"
                    )
                    self.logger.error(
                        "Invalid parameters in {} hangup API call: {}".format(
                            self.vendor_type, error_message
                        )
                    )
                    raise ValueError(INVALID_PARAMETER.format(error_message))
                else:
                    self.logger.error(
                        "Unexpected {} hangup API response: {} - {}".format(
                            self.vendor_type, response.status_code, response.text
                        )
                    )
                    raise ValueError(
                        UNEXPECTED_API_RESPONSE.format(response.status_code)
                    )
        except ValueError:
            raise
        except Exception as e:
            self.logger.error(
                "Failed to make {} hangup API call: {}".format(self.vendor_type, str(e))
            )
            raise ValueError(
                "{} hangup API call failed: {}".format(self.vendor_type, str(e))
            )

    async def transfer_call(self, call_id: str, destination_number: str) -> dict:
        """
        Transfer an in-progress call using Tata Tele's call options API.

        Args:
            call_id: Tata Tele's identifier for the in-progress call.
            destination_number: Number to transfer the call to.

        Returns:
            dict: API response from Tata Tele.

        Raises:
            ValueError: If transfer_url_handler is not configured, or the API call fails.
        """
        try:
            self.logger.info(
                "{} transfer_call started. call_id={} destination={}".format(
                    self.vendor_type, call_id, destination_number
                )
            )

            transfer_handler: dict = self.vendor_config.get("transfer_url_handler", {})
            if not transfer_handler:
                raise ValueError(TRANSFER_URL_HANDLER_NOT_CONFIGURED)

            endpoint: str = transfer_handler["endpoint"]
            auth_credentials: dict = transfer_handler.get("auth_credentials", {})

            payload: dict = {
                "type": 4,
                "call_id": call_id,
                "intercom": normalize_phone_number(destination_number, with_plus=False),
            }

            headers: dict = {
                "Content-Type": "application/json",
                "Authorization": auth_credentials.get("token"),
            }

            async with httpx.AsyncClient() as client:
                self.logger.info(
                    "Making {} transfer API call to {}".format(
                        self.vendor_type, endpoint
                    )
                )
                response = await client.post(endpoint, json=payload, headers=headers)
                self.logger.debug(
                    "{} transfer response={}".format(self.vendor_type, response)
                )
                if response.status_code == 200:
                    json_data = response.json()
                    self.logger.info(
                        "{} transfer API call successful: {}".format(
                            self.vendor_type, json_data
                        )
                    )
                    return json_data
                elif response.status_code == 400:
                    error_data = response.json()
                    error_message = error_data.get("message")
                    self.logger.error(
                        "Invalid parameters in {} transfer API call: {}".format(
                            self.vendor_type, error_message
                        )
                    )
                    raise ValueError(INVALID_PARAMETER.format(error_message))
                else:
                    self.logger.error(
                        "Unexpected {} transfer API response: {} - {}".format(
                            self.vendor_type, response.status_code, response.text
                        )
                    )
                    raise ValueError(
                        UNEXPECTED_API_RESPONSE.format(response.status_code)
                    )
        except Exception as e:
            self.logger.error(
                "Failed to make {} transfer API call: {}".format(
                    self.vendor_type, str(e)
                )
            )
            raise ValueError(
                "{} transfer API call failed: {}".format(self.vendor_type, str(e))
            )

    async def find_live_call_id(
        self,
        did_number: str,
        customer_number: str,
        max_attempts: int = 3,
        poll_interval: float = 0.25,
    ) -> Optional[str]:
        """
        Best-effort lookup of a Tata call_id for a call that's still ringing
        or connecting, via the live_calls API.

        This exists only because click_to_call_support (AI-bridge mode) never
        returns a call_id synchronously — Tata's own docs confirm this. It is
        an optimization, not a required step: never raises, always returns
        None on any failure or if not configured, so callers can proceed with
        their existing fallback behaviour unchanged.

        Args:
            did_number: Caller ID (from_number) — used to filter the live_calls
                        query server-side.
            customer_number: Customer number (to_number) — matched client-side
                        against each candidate's customer_number, since
                        live_calls has no customer_number filter param.
            max_attempts: Number of poll attempts.
            poll_interval: Seconds to wait between attempts.

        Returns:
            The matched call_id, or None if not found / not configured / any
            request failed.
        """
        live_calls_config: dict = self.vendor_config.get("live_calls_url_handler", {})
        if not live_calls_config:
            self.logger.debug(
                "{} live_calls_url_handler not configured — skipping live "
                "call_id lookup".format(self.vendor_type)
            )
            return None

        endpoint: str = live_calls_config.get("endpoint")
        auth_credentials: dict = live_calls_config.get("auth_credentials", {})
        headers: dict = {
            **live_calls_config.get("headers", {}),
            "Authorization": auth_credentials.get("token"),
        }
        normalized_customer: str = customer_number[-10:] if customer_number else ""

        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                for attempt in range(max_attempts):
                    try:
                        response = await client.get(
                            endpoint,
                            params={"did_number": did_number},
                            headers=headers,
                        )
                        if response.status_code == 200:
                            data: Any = response.json()
                            results: List[Dict[str, Any]] = (
                                data.get("results", [])
                                if isinstance(data, dict)
                                else (data or [])
                            )
                            for call in results:
                                candidate = str(call.get("customer_number") or "")
                                if (
                                    normalized_customer
                                    and candidate[-10:] == normalized_customer
                                ):
                                    found_call_id = call.get("call_id")
                                    if found_call_id:
                                        self.logger.info(
                                            "{} live_calls resolved call_id={} "
                                            "attempt={}".format(
                                                self.vendor_type,
                                                found_call_id,
                                                attempt + 1,
                                            )
                                        )
                                        return str(found_call_id)
                        else:
                            self.logger.debug(
                                "{} live_calls poll attempt={} status={}".format(
                                    self.vendor_type, attempt + 1, response.status_code
                                )
                            )
                    except Exception as e:
                        self.logger.debug(
                            "{} live_calls poll attempt={} failed: {}".format(
                                self.vendor_type, attempt + 1, str(e)
                            )
                        )

                    if attempt < max_attempts - 1:
                        await asyncio.sleep(poll_interval)
        except Exception as e:
            self.logger.warning(
                "{} live_calls lookup failed entirely: {}".format(
                    self.vendor_type, str(e)
                )
            )
            return None

        self.logger.info(
            "{} live_calls did not resolve call_id within {} attempts for "
            "customer_number={}".format(self.vendor_type, max_attempts, customer_number)
        )
        return None
