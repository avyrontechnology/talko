from typing import Any, Dict, Optional

from pydantic import BaseModel, field_validator, model_validator
from pydantic_core import PydanticCustomError

from src.components.call_management.enums import TalkoOutboundType
from src.components.cdr.constants import TalkoEntityType


class TalkoContract:
    class CallCreate(BaseModel):
        entity_type: Optional[TalkoEntityType] = None  # "Lead" or "Contact"
        entity_id: Optional[int] = None
        entity_name: Optional[str] = None

        # ── DEPRECATED: kept for backward compat (old callers) ─────────
        lead_id: Optional[int] = None
        lead_name: Optional[str] = None

        service_board_id: Optional[int] = None
        partner_id: Optional[int] = None
        number_type: Optional[str] = None
        lead_secret: Optional[str] = None
        cloud_agent_number: Optional[str] = None
        outbound_type: Optional[str] = None
        agent_number: Optional[str] = None
        to_number: Optional[str] = None
        call_url: Optional[str] = None
        encryption_enabled: Optional[bool] = None
        dedicated_did: Optional[str] = None
        enable_ai_bridge: Optional[bool] = False
        context_data: Optional[Dict[str, Any]] = None

        # Encryption vs Lead Secret validation
        @model_validator(mode="after")
        def validate_encryption_secret(self):
            if self.encryption_enabled and not self.lead_secret:
                raise PydanticCustomError(
                    "lead_secret_required",
                    "lead_secret is required when encryption is enabled",
                )
            return self

        # To-number required when encryption is disabled
        @model_validator(mode="after")
        def validate_to_number(self):
            if not self.encryption_enabled and not self.to_number:
                raise PydanticCustomError(
                    "to_number_required",
                    "to_number is required when encryption is disabled",
                )
            return self

        # Outbound type validation
        @model_validator(mode="after")
        def validate_outbound_type(self):
            if (
                self.outbound_type
                and self.outbound_type not in TalkoOutboundType._value2member_map_
            ):
                raise PydanticCustomError(
                    "invalid_outbound_type",
                    f"Invalid outbound_type. Allowed values are: "
                    f"{', '.join(TalkoOutboundType._value2member_map_.keys())}",
                )
            return self

        # Agent number mandatory
        @model_validator(mode="after")
        def validate_agent_number(self):
            # agent_number is NOT required when enable_ai_bridge=True
            # because AI is the agent — no human agent number needed
            if not self.enable_ai_bridge and not self.agent_number:
                raise PydanticCustomError(
                    "agent_number_required",
                    "agent_number is required for outbound calling",
                )
            return self

        # Dedicated DID format validation
        @field_validator("dedicated_did")
        @classmethod
        def validate_dedicated_did_format(cls, v: Optional[str]) -> Optional[str]:
            if v is None:
                return v

            if not v.isdigit() or not (10 <= len(v) <= 15):
                raise PydanticCustomError(
                    "invalid_dedicated_did_format",
                    "dedicated_did must contain only digits and be between 10 to 15 digits "
                    "(e.g. 918889560593)",
                )
            return v

        # Service board mandatory for non-AI calls
        @model_validator(mode="after")
        def validate_service_board_id(self):
            # When not using AI bridge, service_board_id is required
            if not self.enable_ai_bridge and self.service_board_id is None:
                raise PydanticCustomError(
                    "service_board_id_required",
                    "service_board_id is required when enable_ai_bridge is false",
                )
            return self

    class CallResponse(BaseModel):
        id: str
        message: str

    class HangupCallRequest(BaseModel):
        call_id: str
        enable_ai_bridge: Optional[bool] = False

        @field_validator("call_id")
        @classmethod
        def validate_call_id_not_blank(cls, v: str) -> str:
            if not v.strip():
                raise PydanticCustomError(
                    "call_id_required",
                    "call_id is required",
                )
            return v

    class HangupCallResponse(BaseModel):
        success: bool
        message: str

    class CallTransferRequest(BaseModel):
        call_id: str
        destination_number: str
        enable_ai_bridge: Optional[bool] = False

        @field_validator("call_id")
        @classmethod
        def validate_call_id(cls, v: str) -> str:
            if not v or not v.strip():
                raise PydanticCustomError(
                    "call_id_required", "call_id must not be empty"
                )
            return v

        @field_validator("destination_number")
        @classmethod
        def validate_destination_number(cls, v: str) -> str:
            if not v or not v.strip():
                raise PydanticCustomError(
                    "destination_number_required",
                    "destination_number must not be empty",
                )
            return v

    class CallTransferResponse(BaseModel):
        status: str
        message: str
