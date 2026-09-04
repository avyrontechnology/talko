from typing import NamedTuple, Optional

from fastapi import Request

from src.components.common.constants import TalkoCurrentUserMap


class TalkoCurrentAuthContext(NamedTuple):
    """
    Normalized identity extracted from request.state.user.

    For JWT (Bearer token) auth -> both user_id and partner_id are populated.
    For API-KEY auth            -> only partner_id is populated; user_id is None.
    """

    user_id: Optional[int]
    partner_id: Optional[int]
    is_api_key_auth: bool


def get_current_auth_context(request: Request) -> TalkoCurrentAuthContext:
    """
    Extract user_id / partner_id from request.state.user in a way that's
    safe for both JWT-authenticated requests and API-KEY-authenticated requests.

    Usage in any controller:
        auth_ctx = get_current_auth_context(request)
        user_id = auth_ctx.user_id        # None when authenticated via API key
        partner_id = auth_ctx.partner_id  # always present when authenticated

    Raises:
        ValueError: if request.state.user is missing or partner_id cannot be
                    resolved (should not happen if TalkoAuthMiddleware ran correctly).
    """
    current_user_data: dict = getattr(request.state, "user", None)

    if not current_user_data:
        raise ValueError("request.state.user is not set; auth middleware did not run")

    is_api_key_auth: bool = bool(current_user_data.get("is_api_key_auth", False))

    if is_api_key_auth:
        # API-KEY auth only ever carries partner_id (see TalkoAuthMiddleware._handle_api_key)
        user_id = None
        partner_id = current_user_data.get("partner_id")
    else:
        user_id = current_user_data.get(TalkoCurrentUserMap.USER_ID)
        partner_id = current_user_data.get(TalkoCurrentUserMap.PARTNER_ID)

    if partner_id is None:
        raise ValueError("partner_id could not be resolved from request.state.user")

    return TalkoCurrentAuthContext(
        user_id=user_id,
        partner_id=partner_id,
        is_api_key_auth=is_api_key_auth,
    )
