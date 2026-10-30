"""Create initial tables: python -m app.init_db (PYTHONPATH=backend)."""
import sys

from sqlalchemy.orm import sessionmaker

from . import models  # noqa: F401  (테이블 메타데이터 등록)
from .config import Settings
from .crud.users import create_user, get_user_by_email
from .database import Base, build_engine
from .security import hash_password

ADMIN_PASSWORD_MIN_LENGTH = 8


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
        Base.metadata.create_all(engine)
        print("Database tables ready: users, user_sessions, chat_logs")
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
