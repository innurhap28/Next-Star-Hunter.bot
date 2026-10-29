"""Public error response bodies used in the OpenAPI error examples."""
from typing import Union

from pydantic import BaseModel, ConfigDict


class ErrorResponse(BaseModel):
    """Public error envelope; never includes request input or credentials."""
    model_config = ConfigDict(extra="forbid")
    error: str
    message: str


class ValidationErrorResponse(ErrorResponse):
    """Field locations only, including integer positions for invalid JSON."""
    fields: list[list[Union[str, int]]]
