from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class TalkoContract:
    class LeadListItem(BaseModel):
        id: int = Field(..., description="Unique ID of the broadcast list")
        name: str = Field(..., description="Name of the broadcast list")
        description: str = Field(..., description="Description of the broadcast list")
        field_map: List[str] = Field(..., description="Fields mapped to the list")

        @field_validator("id")
        @classmethod
        def id_must_be_positive(cls, v: int) -> int:
            if v <= 0:
                raise ValueError("id must be a positive integer")
            return v

    class LeadListsFetchResponse(BaseModel):
        status: str = Field(..., description="Response status")
        message: str = Field(..., description="Response message")
        data: Dict[str, List["TalkoContract.LeadListItem"]] = Field(
            ..., description="Data containing lists"
        )

    class LeadObject(BaseModel):
        field_0: str = Field(..., description="Phone number - mandatory")
        field_1: Optional[str] = None
        field_2: Optional[str] = None

    class BulkLeadsCreateRequest(BaseModel):
        data: List["TalkoContract.LeadObject"] = Field(
            ..., description="Required array of leads (at least one)"
        )
        duplicate_option: str = Field(
            "skip", description="How to handle duplicates: skip | overwrite | clone"
        )
        skill_id: Optional[str] = Field(
            None, description="Optional skill ID for outbound routing"
        )

        @model_validator(mode="before")
        @classmethod
        def validate_leads(cls, values):
            data = values.get("data")

            if not data or not isinstance(data, list):
                raise ValueError("data array is required and cannot be empty")

            for index, lead in enumerate(data):
                if not lead or not lead.get("field_0"):
                    raise ValueError(
                        f"Each lead must contain field_0 (phone number). "
                        f"Error at index {index}"
                    )

            return values

        @field_validator("duplicate_option")
        @classmethod
        def validate_duplicate_option(cls, v: str) -> str:
            allowed = {"skip", "overwrite", "clone"}
            if v not in allowed:
                raise ValueError(
                    f"duplicate_option must be one of: {', '.join(allowed)}"
                )
            return v

        @field_validator("data")
        @classmethod
        def data_cannot_be_empty(
            cls, v: List["TalkoContract.LeadObject"]
        ) -> List["TalkoContract.LeadObject"]:
            if not v:
                raise ValueError("data array cannot be empty")
            return v

    class BulkLeadsCreateResponse(BaseModel):
        success: bool = Field(..., description="True if bulk creation succeeded")
        message: str = Field(..., description="Success or error message from Tata API")
