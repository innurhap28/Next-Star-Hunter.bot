"""Check local authentication readiness without displaying credentials.

Run from the repository root: python backend/check_local.py
Create tables separately: PYTHONPATH=backend python -m app.init_db
"""
import json

from sqlalchemy import inspect, text

from app.config import Settings
from app.database import build_engine


def check_local(settings=None):
    settings = settings or Settings()
    missing = []
    if len(settings.SECRET_KEY.get_secret_value()) < 32:
        missing.append("SECRET_KEY (at least 32 characters)")
    if not settings.DATABASE_URL.get_secret_value():
        missing.append("DATABASE_URL")
    if missing:
        return {"ready": False, "error": "AUTH_NOT_CONFIGURED", "missing": missing}
    engine = None
    try:
        engine = build_engine(settings.DATABASE_URL.get_secret_value())
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            db = inspect(connection)
            tables = {name: db.has_table(name) for name in ("users", "chat_logs")}
        if not all(tables.values()):
            return {"ready": False, "error": "DB_TABLES_MISSING", "tables": tables,
                    "next_step": "Set PYTHONPATH=backend and run python -m app.init_db"}
        return {"ready": True, "database": "PostgreSQL", "tables": tables}
    except Exception as error:
        # Exception messages may contain connection strings or credentials.
        # build_engine rejects non-PostgreSQL URLs, which the API reports as DB_NOT_CONFIGURED.
        invalid_url = engine is None and isinstance(error, ValueError)
        code = "DB_NOT_CONFIGURED" if invalid_url else "DB_UNAVAILABLE"
        return {"ready": False, "error": code, "error_type": type(error).__name__}
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    result = check_local()
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result["ready"] else 1)
