"""HTTP/account tests with an injected isolated in-memory DB.

SQLite here is a test double for the ORM; production accepts PostgreSQL only.
A separate opt-in test verifies the PostgreSQL driver and database path.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.database import Base
from app.main import create_app
from app.models import User
from app.security import verify_password

ACCOUNT = {"email": "tester@example.com", "password": "safe-test-password-123"}

@pytest.fixture
def setup():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        _env_file=None,
        SECRET_KEY="test-only-signing-secret-at-least-32-characters",
        DATABASE_URL="postgresql+psycopg://unused:unused@localhost/test",
        SESSION_HTTPS_ONLY=True,
    )
    with TestClient(create_app(settings, factory), base_url="https://testserver") as client:
        yield client, factory
    engine.dispose()

def test_register_login_me_and_logout(setup):
    client, factory = setup
    assert client.get("/api/me").status_code == 401
    r = client.post("/api/auth/register", json=ACCOUNT)
    assert r.status_code == 201
    assert set(r.json()) == {"id", "email", "created_at"}
    assert "password" not in r.text
    # Register does not silently log in.
    assert client.get("/api/me").status_code == 401
    with factory() as db:
        user = db.scalar(select(User))
        assert user.password_hash != ACCOUNT["password"]
        assert verify_password(ACCOUNT["password"], user.password_hash)
    r = client.post("/api/auth/login", json=ACCOUNT)
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert all(flag in cookie for flag in ("httponly", "secure", "samesite=lax"))
    assert client.get("/api/me").json()["email"] == ACCOUNT["email"]
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/me").status_code == 401

def test_duplicate_email_is_case_insensitive(setup):
    client, _ = setup
    assert client.post("/api/auth/register", json=ACCOUNT).status_code == 201
    duplicate = {**ACCOUNT, "email": "TESTER@EXAMPLE.COM"}
    assert client.post("/api/auth/register", json=duplicate).status_code == 409

@pytest.mark.parametrize(
    "email,password",
    [("missing@example.com", ACCOUNT["password"]), (ACCOUNT["email"], "wrong-password-123")],
)
def test_failed_login_is_generic(setup, email, password):
    client, _ = setup
    client.post("/api/auth/register", json=ACCOUNT)
    r = client.post("/api/auth/login", json={"email":email,"password":password})
    assert r.status_code == 401
    assert r.json()["error"] == "INVALID_CREDENTIALS"
    assert client.get("/api/me").status_code == 401

def test_validation_error_does_not_echo_password(setup):
    client, _ = setup
    r = client.post("/api/auth/register", json={**ACCOUNT, "email":"bad-email", "extra": "secret"})
    assert r.status_code == 422
    assert ACCOUNT["password"] not in r.text
    assert "secret" not in r.text

def test_tampered_session_cannot_authenticate(setup):
    client, _ = setup
    client.post("/api/auth/register", json=ACCOUNT)
    client.post("/api/auth/login", json=ACCOUNT)
    client.cookies.clear()
    client.cookies.set("next_star_session", "tampered-value")
    assert client.get("/api/me").status_code == 401

def test_different_origin_login_is_blocked(setup):
    client, _ = setup
    r = client.post("/api/auth/register", json=ACCOUNT, headers={"Origin":"https://untrusted.example"})
    assert r.status_code == 403
    trusted = {"Origin": "https://testserver"}
    assert client.post("/api/auth/register", json=ACCOUNT, headers=trusted).status_code == 201

def test_database_failure_is_safe_and_health_survives(setup, monkeypatch):
    client, factory = setup
    def fail(*args, **kwargs):
        raise OperationalError("secret SQL", {}, Exception("password=do-not-leak"))
    monkeypatch.setattr(factory.class_, "scalar", fail)
    r = client.post("/api/auth/login", json=ACCOUNT)
    assert r.status_code == 503
    assert r.json()["error"] == "DB_UNAVAILABLE"
    assert "do-not-leak" not in r.text
    assert client.get("/health").status_code == 200

def test_health_runs_without_auth_configuration():
    settings = Settings(_env_file=None, SECRET_KEY="", DATABASE_URL="", ENABLE_API_DOCS=False)
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").json() == {"status":"ok","service":"next-star-hunter"}
        assert client.get("/docs").status_code == 404
        r = client.post("/api/auth/login", json=ACCOUNT)
        assert r.status_code == 503
        assert r.json()["error"] == "AUTH_NOT_CONFIGURED"

def test_two_users_receive_their_own_identity(setup):
    client, _ = setup
    client.post("/api/auth/register", json=ACCOUNT)
    client.post("/api/auth/register", json={**ACCOUNT,"email":"second@example.com"})
    client.post("/api/auth/login", json=ACCOUNT)
    first = client.get("/api/me").json()["id"]
    client.post("/api/auth/login", json={**ACCOUNT,"email":"second@example.com"})
    second = client.get("/api/me").json()
    assert second["id"] != first
    assert second["email"] == "second@example.com"

def test_request_ids_and_no_password_logs(setup, caplog):
    client, _ = setup
    with caplog.at_level("INFO", logger="next_star_hunter"):
        r = client.post("/api/auth/register", json=ACCOUNT)
    assert r.headers["x-request-id"]
    assert ACCOUNT["password"] not in caplog.text
    assert "request_received" in caplog.text
    assert "db_save_success" in caplog.text

def test_malformed_origin_does_not_crash(setup):
    client, _ = setup
    malformed = {"Origin": "https://["}
    assert client.post("/api/auth/register", json=ACCOUNT, headers=malformed).status_code == 403
