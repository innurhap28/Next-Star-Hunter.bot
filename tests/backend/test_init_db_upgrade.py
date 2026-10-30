"""init_db on a database made before conversations: add the column, backfill once."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    func,
    inspect,
    select,
)
from sqlalchemy.orm import sessionmaker

from app.init_db import BACKFILL_TITLE, upgrade_schema
from app.models import ChatLog, Conversation

BASE_TIME = datetime(2026, 10, 1, 9, 0)


def old_schema(engine):
    """users and chat_logs as they were before conversation_id existed."""
    meta = MetaData()
    users = Table("users", meta,
                  Column("id", Integer, primary_key=True),
                  Column("email", String(254), unique=True, nullable=False),
                  Column("password_hash", String(256), nullable=False),
                  Column("created_at", DateTime(timezone=True), nullable=False))
    logs = Table("chat_logs", meta,
                 Column("id", Integer, primary_key=True),
                 Column("user_id", ForeignKey("users.id"), nullable=False),
                 Column("question", Text, nullable=False),
                 Column("answer", Text, nullable=False),
                 Column("created_at", DateTime(timezone=True), nullable=False))
    meta.create_all(engine)
    with engine.begin() as conn:
        for uid in (1, 2, 3):
            conn.execute(users.insert().values(id=uid, email=f"u{uid}@example.com",
                                               password_hash="h", created_at=BASE_TIME))
        for i, uid in enumerate([1, 1, 1, 2]):
            conn.execute(logs.insert().values(user_id=uid, question=f"q{i}", answer=f"a{i}",
                                              created_at=BASE_TIME + timedelta(minutes=i)))


def snapshot(factory):
    with factory() as db:
        rooms = [(r.id, r.user_id, r.title, r.created_at, r.updated_at)
                 for r in db.scalars(select(Conversation).order_by(Conversation.id))]
        logs = [(log.id, log.conversation_id)
                for log in db.scalars(select(ChatLog).order_by(ChatLog.id))]
    return rooms, logs


def as_utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def test_upgrade_adds_column_and_backfills_once(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    old_schema(engine)
    assert "conversation_id" not in {c["name"] for c in inspect(engine).get_columns("chat_logs")}

    assert upgrade_schema(engine) == {"column_added": True, "conversations_backfilled": 2}
    inspector = inspect(engine)
    assert "conversations" in inspector.get_table_names()
    assert "conversation_id" in {c["name"] for c in inspector.get_columns("chat_logs")}
    assert "ix_chat_logs_conversation_id" in {i["name"] for i in
                                              inspector.get_indexes("chat_logs")}

    factory = sessionmaker(engine, expire_on_commit=False)
    rooms, logs = snapshot(factory)
    # one room per user with logs (user 3 has none), spanning the first and last log
    assert [(user, title) for _, user, title, _, _ in rooms] == [(1, BACKFILL_TITLE),
                                                                (2, BACKFILL_TITLE)]
    first = rooms[0]
    assert as_utc(first[3]) == BASE_TIME.replace(tzinfo=timezone.utc)
    assert as_utc(first[4]) == (BASE_TIME + timedelta(minutes=2)).replace(tzinfo=timezone.utc)
    assert [room for _, room in logs] == [rooms[0][0]] * 3 + [rooms[1][0]]

    # running again changes nothing
    assert upgrade_schema(engine) == {"column_added": False, "conversations_backfilled": 0}
    assert snapshot(factory) == (rooms, logs)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Conversation)) == 2
    engine.dispose()


def test_upgrade_on_a_new_database_makes_nothing(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'new.db'}")
    assert upgrade_schema(engine) == {"column_added": False, "conversations_backfilled": 0}
    assert upgrade_schema(engine) == {"column_added": False, "conversations_backfilled": 0}
    engine.dispose()
