"""DELETE /api/me/chats/{chat_id} with in-memory SQLite."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.database import Base
from app.main import create_app
from app.models import ChatLog, User

ACCOUNT = {"email": "delete-user@example.com", "password": "delete-test-password-123"}
OTHER = {"email": "delete-other@example.com", "password": "delete-other-password-123"}
NOT_FOUND = {"error": "CHAT_NOT_FOUND", "message": "대화를 찾을 수 없습니다."}


@pytest.fixture
def setup():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    settings = Settings(_env_file=None,
                        SECRET_KEY="delete-test-signing-secret-at-least-32-characters",
                        DATABASE_URL="postgresql+psycopg://unused:unused@localhost/test",
                        SESSION_HTTPS_ONLY=True, ENABLE_API_DOCS=True)
    with TestClient(create_app(settings, factory), base_url="https://testserver") as client:
        client.post("/api/auth/register", json=ACCOUNT)
        client.post("/api/auth/register", json=OTHER)
        yield client, factory
    engine.dispose()


def add_chat(factory, email, question="q"):
    with factory() as db:
        uid = db.scalar(select(User.id).where(User.email == email))
        row = ChatLog(user_id=uid, question=question, answer="a")
        db.add(row)
        db.commit()
        return row.id


def remaining(factory):
    with factory() as db:
        return sorted(db.scalars(select(ChatLog.id)).all())


def test_delete_own_chat(setup):
    client, factory = setup
    mine, keep = add_chat(factory, ACCOUNT["email"]), add_chat(factory, ACCOUNT["email"])
    client.post("/api/auth/login", json=ACCOUNT)
    r = client.delete(f"/api/me/chats/{mine}")
    assert r.status_code == 204 and r.content == b""
    assert remaining(factory) == [keep]
    assert [i["id"] for i in client.get("/api/me/chats").json()["items"]] == [keep]
    # Deleting again is a 404, not a 204.
    assert client.delete(f"/api/me/chats/{mine}").json() == NOT_FOUND


def test_other_users_chat_is_404_and_kept(setup):
    client, factory = setup
    theirs = add_chat(factory, OTHER["email"])
    client.post("/api/auth/login", json=ACCOUNT)
    r = client.delete(f"/api/me/chats/{theirs}")
    assert r.status_code == 404
    assert r.json() == NOT_FOUND
    assert remaining(factory) == [theirs]


def test_missing_chat_is_404(setup):
    client, _ = setup
    client.post("/api/auth/login", json=ACCOUNT)
    r = client.delete("/api/me/chats/9999")
    assert r.status_code == 404
    assert r.json() == NOT_FOUND


def test_login_required(setup):
    client, factory = setup
    chat_id = add_chat(factory, ACCOUNT["email"])
    r = client.delete(f"/api/me/chats/{chat_id}")
    assert r.status_code == 401
    assert r.json()["error"] == "LOGIN_REQUIRED"
    assert remaining(factory) == [chat_id]


def test_replaced_session_cannot_delete(setup):
    client, factory = setup
    chat_id = add_chat(factory, ACCOUNT["email"])
    client.post("/api/auth/login", json=ACCOUNT)
    other_browser = TestClient(client.app, base_url="https://testserver")
    other_browser.post("/api/auth/login", json=ACCOUNT)
    r = client.delete(f"/api/me/chats/{chat_id}")
    assert r.status_code == 401
    assert r.json()["error"] == "SESSION_REPLACED"
    assert remaining(factory) == [chat_id]


def test_cross_origin_delete_is_blocked(setup):
    client, factory = setup
    chat_id = add_chat(factory, ACCOUNT["email"])
    client.post("/api/auth/login", json=ACCOUNT)
    r = client.delete(f"/api/me/chats/{chat_id}", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    assert remaining(factory) == [chat_id]


def test_openapi_and_invalid_id(setup):
    client, _ = setup
    operation = client.get("/openapi.json").json()["paths"]["/api/me/chats/{chat_id}"]["delete"]
    assert {int(code) for code in operation["responses"]} == {204, 401, 403, 404, 422, 503}
    declared = operation["responses"]["404"]["content"]["application/json"]
    assert declared["examples"]["chat_not_found"]["value"] == NOT_FOUND
    client.post("/api/auth/login", json=ACCOUNT)
    r = client.delete("/api/me/chats/abc")
    assert r.status_code == 422
    example = operation["responses"]["422"]["content"]["application/json"]["examples"]
    assert r.json() == example["chat_id"]["value"]
