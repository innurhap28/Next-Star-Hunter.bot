"""GET /api/me/chats tests with in-memory SQLite."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.database import Base
from app.main import create_app
from app.models import ChatLog, User

ACCOUNT = {"email": "history-user@example.com", "password": "history-test-password-123"}
BASE_TIME = datetime(2026, 10, 1, tzinfo=timezone.utc)


def make_settings():
    return Settings(_env_file=None,
                    SECRET_KEY="history-test-signing-secret-at-least-32-characters",
                    DATABASE_URL="postgresql+psycopg://unused:unused@localhost/test",
                    SESSION_HTTPS_ONLY=True, ENABLE_API_DOCS=True)


@pytest.fixture
def setup():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    client = TestClient(create_app(make_settings(), factory), base_url="https://testserver")
    with client:
        yield client, factory
    engine.dispose()


def login(client):
    client.post("/api/auth/register", json=ACCOUNT)
    client.post("/api/auth/login", json=ACCOUNT)


def add_logs(factory, count, email=ACCOUNT["email"]):
    with factory() as db:
        user = db.scalar(select(User).where(User.email == email))
        for i in range(count):
            db.add(ChatLog(user_id=user.id, question=f"q{i}", answer=f"a{i}",
                           created_at=BASE_TIME + timedelta(minutes=i)))
        db.commit()


def test_returns_latest_rows_oldest_first(setup):
    client, factory = setup
    login(client)
    add_logs(factory, 25)
    r = client.get("/api/me/chats")
    assert r.status_code == 200
    items = r.json()["items"]
    # Default limit is 20: q5..q24, oldest first.
    assert [item["question"] for item in items] == [f"q{i}" for i in range(5, 25)]
    assert set(items[0]) == {"id", "question", "answer", "created_at"}
    assert items[-1]["answer"] == "a24"

    r = client.get("/api/me/chats", params={"limit": 3})
    assert [item["question"] for item in r.json()["items"]] == ["q22", "q23", "q24"]


def test_only_own_rows(setup):
    client, factory = setup
    with factory() as db:
        db.add(User(email="other@example.com", password_hash="x"))
        db.commit()
    add_logs(factory, 2, email="other@example.com")
    login(client)
    add_logs(factory, 1)
    items = client.get("/api/me/chats").json()["items"]
    assert [item["question"] for item in items] == ["q0"]
    with factory() as db:
        mine = db.scalar(select(User).where(User.email == ACCOUNT["email"]))
        assert db.get(ChatLog, items[0]["id"]).user_id == mine.id


def test_empty_history(setup):
    client, _ = setup
    login(client)
    assert client.get("/api/me/chats").json() == {"items": []}


def test_login_required(setup):
    client, _ = setup
    r = client.get("/api/me/chats")
    assert r.status_code == 401
    assert r.json()["error"] == "LOGIN_REQUIRED"


@pytest.mark.parametrize("limit", ["0", "101", "-1", "abc"])
def test_invalid_limit_is_rejected(setup, limit):
    client, _ = setup
    login(client)
    r = client.get("/api/me/chats", params={"limit": limit})
    assert r.status_code == 422
    assert r.json() == {"error": "VALIDATION_ERROR", "message": "입력 형식을 확인해주세요.",
                        "fields": [["query", "limit"]]}


def test_limit_bounds_are_allowed(setup):
    client, factory = setup
    login(client)
    add_logs(factory, 2)
    assert len(client.get("/api/me/chats", params={"limit": 1}).json()["items"]) == 1
    assert len(client.get("/api/me/chats", params={"limit": 100}).json()["items"]) == 2


def test_openapi_declares_history_errors(setup):
    client, _ = setup
    schema = client.get("/openapi.json").json()
    assert "HTTPValidationError" not in json.dumps(schema)
    responses = schema["paths"]["/api/me/chats"]["get"]["responses"]
    assert {int(code) for code in responses} == {200, 401, 422, 503}
    declared = responses["422"]["content"]["application/json"]
    assert declared["schema"]["$ref"] == "#/components/schemas/ValidationErrorResponse"
    login(client)
    r = client.get("/api/me/chats", params={"limit": 0})
    assert r.json() == declared["examples"]["limit"]["value"]
