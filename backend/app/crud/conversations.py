"""Conversation (chat room) queries. Every lookup is limited to the owner's rows."""
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..models import ChatLog, Conversation

TITLE_LENGTH = 40


def make_title(message: str) -> str:
    """The first question, cut to 40 characters with '…' when it is longer."""
    text = message.strip()
    return text if len(text) <= TITLE_LENGTH else text[:TITLE_LENGTH] + "…"


def get_user_conversation(db: Session, user_id: int,
                          conversation_id: int) -> Optional[Conversation]:
    """None for a missing room and for another user's room alike."""
    return db.scalar(select(Conversation).where(Conversation.id == conversation_id,
                                                Conversation.user_id == user_id))


def list_user_conversations(db: Session, user_id: int, limit: int) -> list[dict]:
    """The user's rooms, most recently updated first, with the number of saved chats."""
    counts = (select(ChatLog.conversation_id, func.count(ChatLog.id).label("chat_count"))
              .where(ChatLog.user_id == user_id)
              .group_by(ChatLog.conversation_id).subquery())
    query = (select(Conversation.id, Conversation.title, Conversation.created_at,
                    Conversation.updated_at,
                    func.coalesce(counts.c.chat_count, 0).label("chat_count"))
             .outerjoin(counts, counts.c.conversation_id == Conversation.id)
             .where(Conversation.user_id == user_id)
             .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
             .limit(limit))
    return [dict(row._mapping) for row in db.execute(query)]


def list_conversation_chats(db: Session, conversation_id: int) -> list[ChatLog]:
    """All rows of one room, oldest first."""
    return list(db.scalars(
        select(ChatLog).where(ChatLog.conversation_id == conversation_id)
        .order_by(ChatLog.created_at, ChatLog.id)
    ).all())


def conversation_answers(db: Session, conversation_id: Optional[int]) -> list[str]:
    """Every answer of the room, oldest first (to skip stars already recommended)."""
    if conversation_id is None:
        return []
    return list(db.scalars(
        select(ChatLog.answer).where(ChatLog.conversation_id == conversation_id)
        .order_by(ChatLog.created_at, ChatLog.id)
    ).all())


def delete_user_conversation(db: Session, user_id: int, conversation_id: int) -> bool:
    """Delete the room and its chats if it belongs to the user.

    The chats are deleted explicitly as well, so this does not depend on the
    database enforcing ON DELETE CASCADE (SQLite in tests does not by default).
    """
    if get_user_conversation(db, user_id, conversation_id) is None:
        return False
    db.execute(delete(ChatLog).where(ChatLog.conversation_id == conversation_id,
                                     ChatLog.user_id == user_id))
    db.execute(delete(Conversation).where(Conversation.id == conversation_id))
    db.commit()
    return True


def delete_if_empty(db: Session, conversation_id: Optional[int]) -> bool:
    """Remove a room that has no chats left. Does not commit."""
    if conversation_id is None:
        return False
    left = db.scalar(select(func.count()).select_from(ChatLog)
                     .where(ChatLog.conversation_id == conversation_id))
    if left:
        return False
    db.execute(delete(Conversation).where(Conversation.id == conversation_id))
    return True
