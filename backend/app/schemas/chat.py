"""Chat request/response contract (POST /api/chat)."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    # Stripped first, so whitespace-only questions are rejected as empty.
    message: str = Field(min_length=1, max_length=1000,
                         examples=["밝은 분위기의 부산 출신 아이돌을 추천해줘"])
    # Missing or null starts a new conversation; otherwise it must be the user's own.
    conversation_id: Optional[int] = Field(default=None, examples=[None])


class ChatResponse(BaseModel):
    # saved is false (id null) when the answer was made but the DB save failed.
    id: Optional[int]
    question: str
    answer: str
    created_at: datetime
    saved: bool
    # The conversation the answer was saved in; null only when the save failed.
    conversation_id: Optional[int]
