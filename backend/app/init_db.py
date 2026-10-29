"""Create initial tables: python -m app.init_db (PYTHONPATH=backend)."""
import sys
from .config import Settings
from .database import Base, build_engine
from . import models  # register metadata

def main():
    engine = None
    try:
        engine = build_engine(Settings().DATABASE_URL.get_secret_value())
        Base.metadata.create_all(engine)
    except Exception as error:
        # Never print a DSN, password or SQLAlchemy exception string.
        print("DB initialization failed (" + type(error).__name__ + "). Check DATABASE_URL and server access.", file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()
    print("Database tables ready: users, chat_logs")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
