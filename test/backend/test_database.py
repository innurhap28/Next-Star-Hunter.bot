import pytest
from sqlalchemy import create_mock_engine
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql
from app.config import Settings
from app.database import Base, build_engine
from app.models import User, ChatLog

def test_postgres_metadata_contains_required_tables_and_timezone():
    ddl = str(CreateTable(User.__table__).compile(dialect=postgresql.dialect()))
    assert "TIMESTAMP WITH TIME ZONE" in ddl
    assert "UNIQUE (email)" in ddl
    assert {"users", "chat_logs"} <= set(Base.metadata.tables)
    assert str(next(iter(ChatLog.__table__.c.user_id.foreign_keys)).target_fullname) == "users.id"

@pytest.mark.parametrize("url", ["", "sqlite:///app.db", "postgresql://u:p@localhost", "not-a-url"])
def test_database_rejects_non_psycopg_urls(url):
    with pytest.raises(ValueError):
        build_engine(url)

def test_engine_creation_is_lazy():
    engine = build_engine("postgresql+psycopg://u:p@127.0.0.1:1/test_database")
    assert engine.dialect.name == "postgresql"
    engine.dispose()

def test_secret_representations_are_masked():
    settings = Settings(_env_file=None, SECRET_KEY="secret-for-test-only-32-characters-long", DATABASE_URL="postgresql+psycopg://u:sensitive@host/db")
    assert "sensitive" not in repr(settings)
    assert "secret-for-test" not in repr(settings)

@pytest.mark.parametrize("prefix", ["postgres", "postgresql", "postgresql+psycopg"])
def test_railway_urls_use_psycopg_without_changing_password(prefix):
    engine = build_engine(prefix + "://u:encoded%40password@127.0.0.1:1/test_database")
    assert engine.url.drivername == "postgresql+psycopg"
    assert engine.url.password == "encoded@password"
    engine.dispose()
