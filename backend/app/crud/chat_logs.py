"""Chat log queries: saving Q/A pairs and reading them back per user."""
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..models import ChatLog, User, utc_now


def list_user_chats(db: Session, user_id: int, limit: int) -> list[ChatLog]:
    """The user's latest `limit` rows, oldest first."""
    rows = db.scalars(
        select(ChatLog).where(ChatLog.user_id == user_id)
        .order_by(ChatLog.created_at.desc(), ChatLog.id.desc()).limit(limit)
    ).all()
    return list(reversed(rows))


def recent_chat_pairs(db: Session, user_id: int, limit: int = 5) -> list[ChatLog]:
    """Recent Q/A pairs sent to the AI as conversation context."""
    return list_user_chats(db, user_id, limit)


def save_chat_log(db: Session, user_id: int, question: str, answer: str,
                  created_at: Optional[datetime] = None) -> ChatLog:
    """Insert and commit one Q/A row. On a DB error the session is rolled back and
    the error is raised again; the router decides what the user sees."""
    log = ChatLog(user_id=user_id, question=question, answer=answer,
                  created_at=created_at or utc_now())
    db.add(log)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise
    return log


def delete_user_chat(db: Session, user_id: int, chat_id: int) -> bool:
    """Delete one row only if it belongs to the user. Returns False if nothing was deleted."""
    result = db.execute(delete(ChatLog).where(ChatLog.id == chat_id, ChatLog.user_id == user_id))
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
    query = (select(ChatLog.id, ChatLog.user_id, User.email, ChatLog.question,
                    ChatLog.answer, ChatLog.created_at)
             .join(User, User.id == ChatLog.user_id))
    if user_id is not None:
        query = query.where(ChatLog.user_id == user_id)
    query = query.order_by(ChatLog.created_at.desc(), ChatLog.id.desc()).limit(limit)
    return [dict(row._mapping) for row in db.execute(query)]
