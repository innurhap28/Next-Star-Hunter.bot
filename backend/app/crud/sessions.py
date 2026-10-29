"""Login session rows: one active session per user, latest login wins."""
import hashlib
import hmac
import secrets
from typing import Optional

from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import UserSession, utc_now


def new_session_id() -> str:
    return secrets.token_urlsafe(32)


def hash_session_id(session_id: str) -> str:
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()


def get_user_session(db: Session, user_id: int) -> Optional[UserSession]:
    return db.get(UserSession, user_id)


def session_matches(row: Optional[UserSession], session_id: object) -> bool:
    """Constant-time compare of the cookie's session id against the stored hash."""
    if row is None or type(session_id) is not str:
        return False
    return hmac.compare_digest(hash_session_id(session_id), row.session_hash)


def replace_user_session(db: Session, user_id: int, session_id: str) -> UserSession:
    """Store the new session for the user, replacing any previous one, and commit."""
    row = db.get(UserSession, user_id)
    if row is None:
        row = UserSession(user_id=user_id)
        db.add(row)
    row.session_hash, row.created_at = hash_session_id(session_id), utc_now()
    try:
        db.commit()
    except IntegrityError:
        # Another login for the same user inserted first; overwrite its row.
        db.rollback()
        row = db.get(UserSession, user_id)
        row.session_hash, row.created_at = hash_session_id(session_id), utc_now()
        db.commit()
    return row


def delete_user_session(db: Session, user_id: int, session_id: object) -> bool:
    """Delete the row only when it still belongs to this session. Returns True if deleted."""
    row = db.get(UserSession, user_id)
    if not session_matches(row, session_id):
        return False
    db.execute(delete(UserSession).where(UserSession.user_id == user_id,
                                         UserSession.session_hash == row.session_hash))
    db.commit()
    return True
