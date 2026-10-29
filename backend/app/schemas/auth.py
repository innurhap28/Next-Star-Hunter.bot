"""Explicit authentication request/response contract."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Swagger "Try it out" fills in these values, so they must pass validation.
    email: EmailStr = Field(max_length=254, examples=["user@example.com"])
    password: str = Field(min_length=8, max_length=128, repr=False, examples=["password1234"])

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        return str(value).casefold()

    @field_validator("password")
    @classmethod
    def validate_password(cls, value):
        if not value.strip():
            raise ValueError("Password must not be blank")
        try:
            value.encode("utf-8")
        except UnicodeError:
            raise ValueError("Password contains invalid Unicode") from None
        return value

class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    created_at: datetime
