from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from src.components.user_auth.models import TalkoUserRole

# Same strength rule as console signup.
_PASSWORD_REGEX = r"^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[!@#$%^&*(),.?\":{}|<>]).{8,}$"


class TalkoContract:
    class Signup(BaseModel):
        name: str = Field(..., min_length=1, max_length=120)
        email: EmailStr
        phone: Optional[str] = Field(default=None, max_length=20)
        password: str = Field(..., min_length=8, max_length=128)

        @field_validator("password")
        @classmethod
        def strong_password(cls, value: str) -> str:
            import re

            if not re.match(_PASSWORD_REGEX, value):
                raise ValueError(
                    "Password needs 8+ chars with upper, lower, digit and special"
                )
            return value

        @field_validator("email")
        @classmethod
        def normalize_email(cls, value: str) -> str:
            return value.strip().lower()

    class AdminCreateUser(BaseModel):
        """Superadmin-provisioned account (credentials handed over offline)."""

        name: str = Field(..., min_length=1, max_length=120)
        email: EmailStr
        phone: Optional[str] = Field(default=None, max_length=20)
        password: str = Field(..., min_length=8, max_length=128)
        role: str = TalkoUserRole.VIEWER
        partner_id: Optional[int] = None

        @field_validator("password")
        @classmethod
        def strong_password(cls, value: str) -> str:
            import re

            if not re.match(_PASSWORD_REGEX, value):
                raise ValueError(
                    "Password needs 8+ chars with upper, lower, digit and special"
                )
            return value

        @field_validator("email")
        @classmethod
        def normalize_email(cls, value: str) -> str:
            return value.strip().lower()

        @field_validator("role")
        @classmethod
        def known_role(cls, value: str) -> str:
            if value not in TalkoUserRole.ALL:
                raise ValueError("Unknown role: {}".format(value))
            return value

    class Login(BaseModel):
        credential: str = Field(..., min_length=1, description="Email address")
        password: str = Field(..., min_length=1)

        @field_validator("credential")
        @classmethod
        def normalize_credential(cls, value: str) -> str:
            return value.strip().lower()

    class UserResponse(BaseModel):
        id: str
        email: str
        name: str
        phone: Optional[str] = None
        role: str
        partner_id: Optional[int] = None
        is_active: bool

    class UpdateUser(BaseModel):
        role: Optional[str] = None
        partner_id: Optional[int] = None
        is_active: Optional[bool] = None

        @field_validator("role")
        @classmethod
        def known_role(cls, value: Optional[str]) -> Optional[str]:
            if value is not None and value not in TalkoUserRole.ALL:
                raise ValueError("Unknown role: {}".format(value))
            return value

    class TokenResponse(BaseModel):
        token: str
        token_type: str = "bearer"
