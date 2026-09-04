from typing import Any, Dict, List, Optional

from src.components.did_management.constants import (
    ADMIN_ACTION_MARK_SPAMMED,
    ADMIN_ACTION_SET_AVAILABLE,
    ADMIN_ACTION_SET_MAPPED,
    COOLDOWN_MS,
    DIDStatus,
)
from src.components.did_management.dto import Contract


class DidStatusUpdateHelper:
    """
    Helper class containing logic for different DID status update actions.
    Separates action handling from the main service to reduce complexity.
    """

    @staticmethod
    def handle_set_available(
        current_status: str, payload: Contract.AdminDIDAction, now: int
    ) -> Dict[str, Any]:
        allowed = {
            DIDStatus.AVAILABLE.value,
            DIDStatus.MAPPED.value,
            DIDStatus.COOLDOWN_COMPLETED.value,
        }
        if current_status not in allowed:
            raise ValueError(
                "INVALID_TRANSITION|Transition from {} to Available is not allowed.".format(
                    current_status
                )
            )
        return {"status": DIDStatus.AVAILABLE.value}

    @staticmethod
    def handle_set_mapped(
        current_status: str, payload: Contract.AdminDIDAction, now: int
    ) -> Dict[str, Any]:
        allowed = {
            DIDStatus.AVAILABLE.value,
            DIDStatus.MAPPED.value,
            DIDStatus.COOLDOWN_COMPLETED.value,
        }
        if current_status not in allowed:
            raise ValueError(
                "INVALID_TRANSITION|Transition from {} to Mapped is not allowed.".format(
                    current_status
                )
            )
        update = {"status": DIDStatus.MAPPED.value}
        if payload.agent_id:
            update.update({"agent_id": payload.agent_id, "mapped_date": now})
        return update

    @staticmethod
    def handle_mark_spammed(
        current_status: str, payload: Contract.AdminDIDAction, now: int
    ) -> Dict[str, Any]:
        if current_status == DIDStatus.AVAILABLE.value:
            raise ValueError(
                "INVALID_STATUS|DID is already AVAILABLE; cannot move directly to Cooling Period."
            )
        return {
            "status": DIDStatus.COOLING_PERIOD.value,
            "cooldown_until": now + COOLDOWN_MS,
            "last_spam_detected_at": now,
        }

    @staticmethod
    def error_result(
        did_number: str, reason: str, code: str = "UNKNOWN_ERROR"
    ) -> Dict[str, Any]:
        return {
            "did_number": did_number,
            "success": False,
            "status": "skipped",
            "error": {"code": code, "message": reason},
        }

    @staticmethod
    def validate_did(
        doc: Optional[Dict], did_number: str, current_status: str, action: str
    ) -> Optional[Dict]:
        """
        Validates DID document and status before update.
        Returns error_result dict if invalid, None if valid.
        """
        if not doc:
            return DidStatusUpdateHelper.error_result(
                did_number, "DID not found for partner", "DID_NOT_FOUND"
            )
        if current_status == DIDStatus.COOLING_PERIOD.value:
            return DidStatusUpdateHelper.error_result(
                did_number,
                "Cannot modify during active Cooling Period",
                "COOLING_PERIOD_ACTIVE",
            )
        if action not in DidStatusUpdateHelper.ACTION_HANDLERS:
            return DidStatusUpdateHelper.error_result(
                did_number, "Invalid action: {}".format(action), "INVALID_ACTION"
            )
        return None

    @staticmethod
    def prepare_update_data(
        handler, current_status: str, payload: Contract.AdminDIDAction, now: int
    ) -> Dict[str, Any]:
        """Build final update_data dict from handler output."""
        update_data = handler(current_status, payload, now)
        if payload.service_board_id is not None:
            update_data["service_board_id"] = payload.service_board_id
        update_data["status_changed_at"] = now
        return update_data

    @staticmethod
    def parse_value_error(did_number: str, e: ValueError) -> Dict[str, Any]:
        """Parse code|message format from ValueError and return error_result."""
        parts = str(e).split("|", 1)
        code = parts[0] if len(parts) == 2 else "VALIDATION_ERROR"
        message = parts[1] if len(parts) == 2 else parts[0]
        return DidStatusUpdateHelper.error_result(did_number, message, code)

    @staticmethod
    def build_summary(did_numbers: List[str], results: List[Dict]) -> Dict[str, Any]:
        """Build final summary + results response dict."""
        succeeded = sum(1 for r in results if r.get("success"))
        return {
            "summary": {
                "total": len(did_numbers),
                "succeeded": succeeded,
                "failed": len(results) - succeeded,
            },
            "results": results,
        }


DidStatusUpdateHelper.ACTION_HANDLERS = {
    ADMIN_ACTION_SET_AVAILABLE: DidStatusUpdateHelper.handle_set_available,
    ADMIN_ACTION_SET_MAPPED: DidStatusUpdateHelper.handle_set_mapped,
    ADMIN_ACTION_MARK_SPAMMED: DidStatusUpdateHelper.handle_mark_spammed,
}
