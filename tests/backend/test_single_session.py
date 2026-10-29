"""One active session per account: the latest login wins."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.crud.sessions import hash_session_id
from app.database import Base
from app.main import create_app
from app.models import UserSession

ACCOUNT = {"email": "single@example.com", "password": "safe-test-password-123"}
REPLACED = {"error": "SESSION_REPLACED", "message": "다른 곳에서 로그인되어 로그아웃되었습니다."}


@pytest.fixture
def app_and_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    settings = Settings(_env_file=None,
                        SECRET_KEY="test-only-signing-secret-at-least-32-characters",
                        DATABASE_URL="postgresql+psycopg://unused:unused@localhost/test")
    yield create_app(settings, factory), factory
    engine.dispose()


@pytest.fixture
def clients(app_and_factory):
    app, factory = app_and_factory
    with TestClient(app, follow_redirects=False) as first, \
            TestClient(app, follow_redirects=False) as second:
        assert first.post("/api/auth/register", json=ACCOUNT).status_code == 201
        assert first.post("/api/auth/login", json=ACCOUNT).status_code == 200
        assert second.post("/api/auth/login", json=ACCOUNT).status_code == 200
        yield first, second, factory


def session_rows(factory):
    with factory() as db:
        return db.scalars(select(UserSession)).all()


def test_only_hash_of_session_id_is_stored(clients):
    _, second, factory = clients
    rows = session_rows(factory)
    assert len(rows) == 1
    assert len(rows[0].session_hash) == 64
    cookie = second.cookies.get("next_star_session")
    assert rows[0].session_hash not in cookie


def test_first_login_is_replaced_and_second_still_works(clients):
    first, second, _ = clients
    r = first.get("/api/me")
    assert r.status_code == 401
    assert r.json() == REPLACED
    assert second.get("/api/me").json()["email"] == ACCOUNT["email"]
    # The replaced cookie was cleared, so the next call is a plain login-required error.
    assert first.get("/api/me").json()["error"] == "LOGIN_REQUIRED"


def test_replaced_session_cannot_chat(clients):
    first, second, _ = clients
    r = first.post("/api/chat", json={"message": "부산 출신 배우 추천해줘"})
    assert r.status_code == 401
    assert r.json() == REPLACED
    assert second.get("/api/me/chats").status_code == 200


def test_logout_of_old_session_keeps_new_row(clients):
    first, second, factory = clients
    before = session_rows(factory)[0].session_hash
    assert first.post("/api/auth/logout").status_code == 401
    assert session_rows(factory)[0].session_hash == before
    assert second.get("/api/me").status_code == 200


def test_logout_removes_own_row(clients):
    _, second, factory = clients
    assert second.post("/api/auth/logout").status_code == 204
    assert session_rows(factory) == []
    assert second.get("/api/me").status_code == 401


def test_relogin_after_replaced_works(clients):
    first, second, _ = clients
    assert first.get("/api/me").status_code == 401
    assert first.post("/api/auth/login", json=ACCOUNT).status_code == 200
    assert first.get("/api/me").status_code == 200
    assert second.get("/api/me").json()["error"] == "SESSION_REPLACED"


def test_chat_page_redirects_with_reason(clients):
    first, second, _ = clients
    r = first.get("/")
    assert r.status_code == 303
    assert r.headers["location"] == "/auth?reason=session_replaced"
    assert first.get("/").headers["location"] == "/auth"
    assert first.get("/auth?reason=session_replaced").status_code == 200
    assert second.get("/").status_code == 200


def test_auth_page_opens_for_replaced_session(clients):
    first, _, _ = clients
    assert first.get("/auth").status_code == 200


def test_cookie_without_matching_row_is_rejected(clients):
    _, second, factory = clients
    with factory() as db:
        db.get(UserSession, session_rows(factory)[0].user_id).session_hash = hash_session_id("x")
        db.commit()
    # A changed row means another login, so the old cookie is replaced.
    assert second.get("/api/me").json() == REPLACED


def test_cookie_after_row_deleted_needs_login(clients):
    _, second, factory = clients
    with factory() as db:
        db.delete(db.get(UserSession, session_rows(factory)[0].user_id))
        db.commit()
    r = second.get("/api/me")
    assert r.status_code == 401
    assert r.json()["error"] == "LOGIN_REQUIRED"


def test_tampered_cookie_is_still_rejected(clients):
    _, second, _ = clients
    second.cookies.clear()
    second.cookies.set("next_star_session", "tampered-value")
    r = second.get("/api/me")
    assert r.status_code == 401
    assert r.json()["error"] == "LOGIN_REQUIRED"
