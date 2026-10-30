"""crud function tests with in-memory SQLite (no app, no network)."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.crud.chat_logs import list_user_chats, recent_chat_pairs, save_chat_log
from app.crud.users import create_user, get_user, get_user_by_email
from app.database import Base
from app.models import ChatLog, Conversation

BASE_TIME = datetime(2026, 10, 1, tzinfo=timezone.utc)


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    engine.dispose()


def test_create_and_get_user(db):
    user = create_user(db, "crud-user@example.com", "hash-value")
    assert user.id is not None
    assert get_user(db, user.id).email == "crud-user@example.com"
    assert get_user_by_email(db, "crud-user@example.com").id == user.id
    assert get_user_by_email(db, "nobody@example.com") is None
    assert get_user(db, 9999) is None


def test_duplicate_email_raises_and_session_stays_usable(db):
    create_user(db, "dup@example.com", "hash-1")
    with pytest.raises(IntegrityError):
        create_user(db, "dup@example.com", "hash-2")
    # Rolled back inside create_user, so the next query still works.
    assert get_user_by_email(db, "dup@example.com").password_hash == "hash-1"


def test_chat_lists_are_per_user_and_oldest_first(db):
    me = create_user(db, "me@example.com", "h")
    other = create_user(db, "other@example.com", "h")
    room = None
    for i in range(7):
        log = save_chat_log(db, me.id, f"q{i}", f"a{i}", BASE_TIME + timedelta(minutes=i),
                            conversation=room)
        room = room or db.get(Conversation, log.conversation_id)
    save_chat_log(db, other.id, "other-q", "other-a", BASE_TIME + timedelta(hours=1))

    assert [row.question for row in list_user_chats(db, me.id, 3)] == ["q4", "q5", "q6"]
    pairs = recent_chat_pairs(db, me.id, room.id)
    assert [row.question for row in pairs] == ["q2", "q3", "q4", "q5", "q6"]
    assert recent_chat_pairs(db, me.id, None) == []
    # another user's id never returns my rows
    assert recent_chat_pairs(db, other.id, room.id) == []
    assert all(row.user_id == me.id for row in list_user_chats(db, me.id, 100))


def test_save_chat_log_sets_time_when_missing(db):
    user = create_user(db, "time@example.com", "h")
    log = save_chat_log(db, user.id, "질문", "답변")
    assert log.id is not None
    assert log.created_at is not None


def test_save_chat_log_rolls_back_on_db_error(db, monkeypatch):
    user = create_user(db, "fail@example.com", "h")

    def fail():
        raise OperationalError("INSERT", {}, Exception("db down"))

    monkeypatch.setattr(db, "commit", fail)
    with pytest.raises(OperationalError):
        save_chat_log(db, user.id, "q", "a")
    monkeypatch.undo()
    assert db.scalar(select(func.count()).select_from(ChatLog)) == 0
    # the new conversation made for that row is rolled back as well
    assert db.scalar(select(func.count()).select_from(Conversation)) == 0
