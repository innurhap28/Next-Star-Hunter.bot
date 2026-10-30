"""Chat log queries: saving Q/A pairs and reading them back per user or conversation."""
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..models import ChatLog, Conversation, User, utc_now
from .conversations import delete_if_empty, make_title


def list_user_chats(db: Session, user_id: int, limit: int) -> list[ChatLog]:
    """The user's latest `limit` rows, oldest first."""
    rows = db.scalars(
        select(ChatLog).where(ChatLog.user_id == user_id)
        .order_by(ChatLog.created_at.desc(), ChatLog.id.desc()).limit(limit)
    ).all()
    return list(reversed(rows))


def recent_chat_pairs(db: Session, user_id: int, conversation_id: Optional[int],
                      limit: int = 5) -> list[ChatLog]:
    """Recent Q/A pairs of one conversation, sent to the AI as context, oldest first.

    A new conversation (None) has no context. Other conversations are never mixed in.
    """
    if conversation_id is None:
        return []
    rows = db.scalars(
        select(ChatLog).where(ChatLog.user_id == user_id,
                              ChatLog.conversation_id == conversation_id)
        .order_by(ChatLog.created_at.desc(), ChatLog.id.desc()).limit(limit)
    ).all()
    return list(reversed(rows))


def save_chat_log(db: Session, user_id: int, question: str, answer: str,
                  created_at: Optional[datetime] = None, *,
                  conversation: Optional[Conversation] = None) -> ChatLog:
    """Insert and commit one Q/A row in a conversation.

    Without a conversation a new one is made from the question in the same commit,
    so a failed AI call or save never leaves an empty room behind. The room's
    updated_at becomes the row's time. On a DB error the session is rolled back and
    the error is raised again; the router decides what the user sees.
    """
    created_at = created_at or utc_now()
    if conversation is None:
        conversation = Conversation(user_id=user_id, title=make_title(question),
                                    created_at=created_at, updated_at=created_at)
        db.add(conversation)
    else:
        conversation.updated_at = created_at
    log = ChatLog(user_id=user_id, question=question, answer=answer, created_at=created_at)
    try:
        db.flush()
        log.conversation_id = conversation.id
        db.add(log)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    return log


def delete_user_chat(db: Session, user_id: int, chat_id: int) -> bool:
    """Delete one row only if it belongs to the user. Returns False if nothing was deleted.

    A conversation left with no chats is deleted too.
    """
    conversation_id = db.scalar(select(ChatLog.conversation_id).where(
        ChatLog.id == chat_id, ChatLog.user_id == user_id))
    result = db.execute(delete(ChatLog).where(ChatLog.id == chat_id, ChatLog.user_id == user_id))
    if result.rowcount > 0:
        delete_if_empty(db, conversation_id)
    db.commit()
    return result.rowcount > 0


def count_chats(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(ChatLog))


def count_chats_today(db: Session, now: Optional[datetime] = None) -> int:
    """Rows created since 00:00 UTC of the current day."""
    now = now or utc_now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return db.scalar(select(func.count()).select_from(ChatLog).where(
        ChatLog.created_at >= start, ChatLog.created_at < start + timedelta(days=1)))


def list_chats_with_email(db: Session, user_id: Optional[int], limit: int) -> list[dict]:
    """Latest rows of all users (or one user), newest first, with the author's email."""
    query = (select(ChatLog.id, ChatLog.user_id, User.email, ChatLog.conversation_id,
                    ChatLog.question, ChatLog.answer, ChatLog.created_at)
             .join(User, User.id == ChatLog.user_id))
    if user_id is not None:
        query = query.where(ChatLog.user_id == user_id)
    query = query.order_by(ChatLog.created_at.desc(), ChatLog.id.desc()).limit(limit)
    return [dict(row._mapping) for row in db.execute(query)]
