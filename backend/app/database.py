"""Lazy PostgreSQL connections; health checks never create a database."""
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

class Base(DeclarativeBase):
    pass

def build_engine(database_url: str):
    try:
        url = make_url(database_url)
        valid = url.drivername in {"postgres", "postgresql", "postgresql+psycopg"} and bool(url.database)
        url = url.set(drivername="postgresql+psycopg")
    except Exception:
        valid = False
    if not valid:
        raise ValueError("DATABASE_URL must be a PostgreSQL URL with a database name")
    return create_engine(url, pool_pre_ping=True, hide_parameters=True,
                         connect_args={"connect_timeout": 5})

def build_session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)
