"""Admin API response contracts (GET /api/admin/*)."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AdminStats(BaseModel):
    users: int
    chats: int
    # Rows saved since 00:00 UTC today.
    chats_today: int


class AdminUserItem(BaseModel):
    id: int
    email: str
    created_at: datetime
    chat_count: int
    last_chat_at: Optional[datetime]


class AdminUserList(BaseModel):
    items: list[AdminUserItem]
    total: int


class AdminChatItem(BaseModel):
    id: int
    user_id: int
    email: str
    # null only for a row the init_db backfill has not reached yet.
    conversation_id: Optional[int]
    question: str
    answer: str
    created_at: datetime


class AdminChatList(BaseModel):
    # Newest first.
    items: list[AdminChatItem]
