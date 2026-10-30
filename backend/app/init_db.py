"""Create or upgrade tables: python -m app.init_db (PYTHONPATH=backend).

Safe to run again on an existing database: missing tables are created,
chat_logs.conversation_id is added if an older schema lacks it, and chat rows
without a conversation are moved into one "이전 대화" room per user.
"""
import sys

from sqlalchemy import func, inspect, select, text, update
from sqlalchemy.orm import sessionmaker

from . import models  # noqa: F401  (테이블 메타데이터 등록)
from .config import Settings
from .crud.users import create_user, get_user_by_email
from .database import Base, build_engine
from .models import ChatLog, Conversation
from .security import hash_password

ADMIN_PASSWORD_MIN_LENGTH = 8
BACKFILL_TITLE = "이전 대화"


def add_conversation_column(engine) -> bool:
    """Add chat_logs.conversation_id (and its index) to a table made before conversations.

    Returns True when the column was added. The index statement uses IF NOT EXISTS,
    so running it again is harmless.
    """
    columns = {c["name"] for c in inspect(engine).get_columns("chat_logs")}
    added = "conversation_id" not in columns
    with engine.begin() as conn:
        if added:
            conn.execute(text(
                "ALTER TABLE chat_logs ADD COLUMN conversation_id INTEGER "
                "REFERENCES conversations(id) ON DELETE CASCADE"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_chat_logs_conversation_id "
                          "ON chat_logs (conversation_id)"))
    return added


def backfill_conversations(session_factory) -> int:
    """Put each user's chat rows without a conversation into one "이전 대화" room.

    The room's created_at/updated_at are the oldest/newest row times. Returns the
    number of rooms made; 0 when there is nothing left to move.
    """
    made = 0
    with session_factory() as db:
        rows = db.execute(
            select(ChatLog.user_id, func.min(ChatLog.created_at), func.max(ChatLog.created_at))
            .where(ChatLog.conversation_id.is_(None))
            .group_by(ChatLog.user_id).order_by(ChatLog.user_id)
        ).all()
        for user_id, first, last in rows:
            room = Conversation(user_id=user_id, title=BACKFILL_TITLE,
                                created_at=first, updated_at=last)
            db.add(room)
            db.flush()
            db.execute(update(ChatLog)
                       .where(ChatLog.user_id == user_id, ChatLog.conversation_id.is_(None))
                       .values(conversation_id=room.id))
            made += 1
        db.commit()
    return made


def upgrade_schema(engine) -> dict:
    """create_all, then the conversation column and backfill. Idempotent."""
    Base.metadata.create_all(engine)
    added = add_conversation_column(engine)
    made = backfill_conversations(sessionmaker(bind=engine, expire_on_commit=False))
    return {"column_added": added, "conversations_backfilled": made}


def seed_admin(session_factory, settings) -> str:
    """Create the ADMIN_EMAIL account if it is missing.

    Returns "skipped", "short_password", "created" or "exists". An existing
    account is never changed, so its password is not overwritten.
    """
    email = settings.admin_email()
    password = settings.ADMIN_PASSWORD.get_secret_value()
    if not email or not password:
        return "skipped"
    if len(password) < ADMIN_PASSWORD_MIN_LENGTH:
        return "short_password"
    with session_factory() as db:
        if get_user_by_email(db, email) is not None:
            return "exists"
        create_user(db, email, hash_password(password))
    return "created"


def main():
    engine = None
    settings = Settings()
    try:
        engine = build_engine(settings.DATABASE_URL.get_secret_value())
        upgrade = upgrade_schema(engine)
        print("Database tables ready: users, user_sessions, conversations, chat_logs")
        if upgrade["column_added"]:
            print("chat_logs.conversation_id added")
        if upgrade["conversations_backfilled"]:
            print("previous chats grouped: "
                  + str(upgrade["conversations_backfilled"]) + " conversation(s)")
        result = seed_admin(sessionmaker(bind=engine, expire_on_commit=False), settings)
    except Exception as error:
        # Never print a DSN, password or SQLAlchemy exception string.
        print(
            "DB initialization failed (" + type(error).__name__ + "). "
            "Check DATABASE_URL and server access.",
            file=sys.stderr,
        )
        return 1
    finally:
        if engine is not None:
            engine.dispose()
    if result == "created":
        print("admin account ready")
    elif result == "exists":
        print("admin account exists")
    elif result == "short_password":
        print("Warning: ADMIN_PASSWORD is shorter than 8 characters; admin account skipped",
              file=sys.stderr)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
