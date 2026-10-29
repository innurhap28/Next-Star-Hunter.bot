"""Create initial tables: python -m app.init_db (PYTHONPATH=backend)."""
import sys

from . import models  # noqa: F401  (테이블 메타데이터 등록)
from .config import Settings
from .database import Base, build_engine


def main():
    engine = None
    try:
        engine = build_engine(Settings().DATABASE_URL.get_secret_value())
        Base.metadata.create_all(engine)
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
    print("Database tables ready: users, user_sessions, chat_logs")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
