from typing import Any

from pydantic import BaseModel, field_validator, model_validator
from pydantic_core import PydanticCustomError

from src.components.call_management.enums import TalkoOutboundType


class TalkoContract:
    class CallCreate(BaseModel):
        workspace_id: int | None = None
        partner_id: int | None = None
        number_type: str | None = None
        lead_secret: str | None = None
        cloud_agent_number: str | None = None
        outbound_type: str | None = None
        agent_number: str | None = None
        to_number: str | None = None
        call_url: str | None = None
        encryption_enabled: bool | None = None
        dedicated_did: str | None = None
        enable_ai_bridge: bool | None = False
        context_data: dict[str, Any] | None = None

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
            if self.outbound_type and self.outbound_type not in TalkoOutboundType._value2member_map_:
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
        def validate_dedicated_did_format(cls, v: str | None) -> str | None:
            if v is None:
                return v

            if not v.isdigit() or not (10 <= len(v) <= 15):
                raise PydanticCustomError(
                    "invalid_dedicated_did_format",
                    "dedicated_did must contain only digits and be between 10 to 15 digits (e.g. 918889560593)",
                )
            return v

        # Workspace mandatory for non-AI calls
        @model_validator(mode="after")
        def validate_workspace_id(self):
            # When not using AI bridge, workspace_id is required
            if not self.enable_ai_bridge and self.workspace_id is None:
                raise PydanticCustomError(
                    "workspace_id_required",
                    "workspace_id is required when enable_ai_bridge is false",
                )
            return self

    class CallResponse(BaseModel):
        id: str
        message: str

    class HangupCallRequest(BaseModel):
        call_id: str
        enable_ai_bridge: bool | None = False

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
        enable_ai_bridge: bool | None = False

        @field_validator("call_id")
        @classmethod
        def validate_call_id(cls, v: str) -> str:
            if not v or not v.strip():
                raise PydanticCustomError("call_id_required", "call_id must not be empty")
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

    class GrpcHangupRequest(BaseModel):
        call_id: str
        vendor_config_id: str = ""

    class GrpcTransferRequest(BaseModel):
        call_id: str
        destination_number: str
        vendor_config_id: str = ""

    class SuperviseRequest(BaseModel):
        call_id: str
        supervisor_id: str
        mode: str = "listen"
        room_name: str | None = None

    class AttendedTransferStart(BaseModel):
        call_id: str
        target_number: str
