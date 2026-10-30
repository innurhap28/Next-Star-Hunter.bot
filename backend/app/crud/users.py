"""User table queries used by signup, login, and the login dependency."""
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import ChatLog, User


def get_user(db: Session, user_id: int) -> Optional[User]:
    return db.get(User, user_id)


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.scalar(select(User).where(User.email == email))


def create_user(db: Session, email: str, password_hash: str) -> User:
    """Insert and commit a user. On a duplicate email the session is rolled back and
    IntegrityError is raised again so the caller can decide the response."""
    user = User(email=email, password_hash=password_hash)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise
    return user


def count_users(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User))


def list_users_with_chat_stats(db: Session, limit: int, offset: int) -> list[dict]:
    """Users in id order with their chat count and latest chat time (one grouped query)."""
    stats = (select(ChatLog.user_id, func.count(ChatLog.id).label("chat_count"),
                    func.max(ChatLog.created_at).label("last_chat_at"))
             .group_by(ChatLog.user_id).subquery())
    query = (select(User.id, User.email, User.created_at,
                    func.coalesce(stats.c.chat_count, 0).label("chat_count"),
                    stats.c.last_chat_at)
             .outerjoin(stats, stats.c.user_id == User.id)
             .order_by(User.id).limit(limit).offset(offset))
    return [dict(row._mapping) for row in db.execute(query)]
