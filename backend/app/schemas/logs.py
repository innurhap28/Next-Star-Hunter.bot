"""Chat history response contract (GET /api/me/chats)."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ChatLogItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    question: str
    answer: str
    created_at: datetime


class ChatHistoryResponse(BaseModel):
    # Latest N rows of the user, ordered oldest first.
    items: list[ChatLogItem]
