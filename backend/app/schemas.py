"""Explicit authentication request/response contract."""
from datetime import datetime
from typing import Optional, Union

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


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    # Stripped first, so whitespace-only questions are rejected as empty.
    message: str = Field(min_length=1, max_length=1000,
                         examples=["밝은 분위기의 부산 출신 아이돌을 추천해줘"])


class ChatResponse(BaseModel):
    # saved is false (id null) when the answer was made but the DB save failed.
    id: Optional[int]
    question: str
    answer: str
    created_at: datetime
    saved: bool


class ChatLogItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    question: str
    answer: str
    created_at: datetime


class ChatHistoryResponse(BaseModel):
    # Latest N rows of the user, ordered oldest first.
    items: list[ChatLogItem]


class ErrorResponse(BaseModel):
    """Public error envelope; never includes request input or credentials."""
    model_config = ConfigDict(extra="forbid")
    error: str
    message: str


class ValidationErrorResponse(ErrorResponse):
    """Field locations only, including integer positions for invalid JSON."""
    fields: list[list[Union[str, int]]]
