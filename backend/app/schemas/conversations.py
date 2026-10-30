"""Conversation (chat room) response contracts (GET /api/me/conversations*)."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from .logs import ChatLogItem


class ConversationItem(BaseModel):
    id: int
    title: str
    created_at: datetime
    updated_at: datetime
    chat_count: int


class ConversationList(BaseModel):
    # The user's own rooms, most recently updated first.
    items: list[ConversationItem]


class ConversationRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str


class ConversationChats(BaseModel):
    conversation: ConversationRef
    # Every chat of the room, oldest first.
    items: list[ChatLogItem]
