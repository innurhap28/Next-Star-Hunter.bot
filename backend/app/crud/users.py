"""User table queries used by signup, login, and the login dependency."""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import User


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
