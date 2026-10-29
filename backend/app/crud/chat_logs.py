"""Chat log queries: saving Q/A pairs and reading them back per user."""
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..models import ChatLog, utc_now


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
