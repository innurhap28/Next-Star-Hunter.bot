"""Admin account, admin read APIs and is_admin on GET /api/me (in-memory SQLite)."""
import json
import logging
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.crud.chat_logs import count_chats_today
from app.database import Base
from app.init_db import seed_admin
from app.main import create_app
from app.models import ChatLog, User
from app.security import verify_password

ADMIN = {"email": "admin@example.com", "password": "admin-test-password-123"}
MEMBER = {"email": "member@example.com", "password": "member-test-password-123"}
BASE_TIME = datetime(2026, 10, 1, 9, tzinfo=timezone.utc)
ADMIN_REQUIRED = {"error": "ADMIN_REQUIRED", "message": "관리자만 사용할 수 있습니다."}


def make_settings(**changes):
    values = dict(SECRET_KEY="admin-test-signing-secret-at-least-32-characters",
                  DATABASE_URL="postgresql+psycopg://unused:unused@localhost/test",
                  SESSION_HTTPS_ONLY=True, ENABLE_API_DOCS=True,
                  ADMIN_EMAIL=ADMIN["email"], ADMIN_PASSWORD=ADMIN["password"])
    values.update(changes)
    return Settings(_env_file=None, **values)


@pytest.fixture
def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


def client_for(factory, **changes):
    return TestClient(create_app(make_settings(**changes), factory),
                      base_url="https://testserver")


@pytest.fixture
def setup(factory):
    seed_admin(factory, make_settings())
    with client_for(factory) as client:
        client.post("/api/auth/register", json=MEMBER)
        yield client, factory


def login(client, account):
    assert client.post("/api/auth/login", json=account).status_code == 200


def user_id(factory, email):
    with factory() as db:
        return db.scalar(select(User.id).where(User.email == email))


def add_chats(factory, email, count, start=BASE_TIME):
    with factory() as db:
        uid = db.scalar(select(User.id).where(User.email == email))
        for i in range(count):
            db.add(ChatLog(user_id=uid, question=f"{email} q{i}", answer=f"a{i}",
                           created_at=start + timedelta(minutes=i)))
        db.commit()


# --- init_db seeding ---------------------------------------------------------

def test_seed_creates_admin_once_and_never_overwrites_password(factory):
    assert seed_admin(factory, make_settings()) == "created"
    assert seed_admin(factory, make_settings(ADMIN_PASSWORD="changed-password-456")) == "exists"
    with factory() as db:
        users = db.scalars(select(User)).all()
    assert [u.email for u in users] == [ADMIN["email"]]
    assert verify_password(ADMIN["password"], users[0].password_hash)
    assert not verify_password("changed-password-456", users[0].password_hash)
    assert ADMIN["password"] not in users[0].password_hash


def test_seed_keeps_existing_account_registered_by_signup(factory):
    with client_for(factory) as client:
        client.post("/api/auth/register", json={**ADMIN, "password": "signup-password-789"})
    assert seed_admin(factory, make_settings()) == "exists"
    with factory() as db:
        row = db.scalar(select(User))
    assert verify_password("signup-password-789", row.password_hash)


def test_seed_normalizes_email_case(factory):
    assert seed_admin(factory, make_settings(ADMIN_EMAIL=" Admin@Example.COM ")) == "created"
    assert user_id(factory, "admin@example.com") is not None


@pytest.mark.parametrize("changes,result", [
    ({"ADMIN_EMAIL": ""}, "skipped"),
    ({"ADMIN_PASSWORD": ""}, "skipped"),
    ({"ADMIN_PASSWORD": "short12"}, "short_password"),
])
def test_seed_skips_without_full_settings(factory, changes, result):
    assert seed_admin(factory, make_settings(**changes)) == result
    with factory() as db:
        assert db.scalar(select(User)) is None


def test_init_db_prints_status_without_password(factory, monkeypatch, capsys):
    from app import init_db
    engine = factory.kw["bind"]
    monkeypatch.setattr(init_db, "Settings", make_settings)
    monkeypatch.setattr(init_db, "build_engine", lambda url: engine)
    monkeypatch.setattr(engine, "dispose", lambda: None)
    assert init_db.main() == 0
    assert init_db.main() == 0
    out = capsys.readouterr()
    assert out.out.count("admin account ready") == 1
    assert out.out.count("admin account exists") == 1
    assert ADMIN["password"] not in out.out + out.err


def test_init_db_warns_on_short_password(factory, monkeypatch, capsys):
    from app import init_db
    engine = factory.kw["bind"]
    monkeypatch.setattr(init_db, "Settings", lambda: make_settings(ADMIN_PASSWORD="short12"))
    monkeypatch.setattr(init_db, "build_engine", lambda url: engine)
    monkeypatch.setattr(engine, "dispose", lambda: None)
    assert init_db.main() == 0
    out = capsys.readouterr()
    assert "admin account" not in out.out
    assert "shorter than 8" in out.err and "short12" not in out.err


# --- GET /api/me is_admin ----------------------------------------------------

def test_me_reports_is_admin(setup):
    client, _ = setup
    login(client, MEMBER)
    assert client.get("/api/me").json()["is_admin"] is False
    login(client, ADMIN)
    body = client.get("/api/me").json()
    assert set(body) == {"id", "email", "created_at", "is_admin"}
    assert body["is_admin"] is True


def test_is_admin_ignores_email_case(factory):
    seed_admin(factory, make_settings())
    with client_for(factory, ADMIN_EMAIL="ADMIN@Example.com") as client:
        login(client, ADMIN)
        assert client.get("/api/me").json()["is_admin"] is True
        assert client.get("/api/admin/stats").status_code == 200


def test_no_admin_when_admin_email_is_empty(factory):
    seed_admin(factory, make_settings())
    with client_for(factory, ADMIN_EMAIL="") as client:
        login(client, ADMIN)
        assert client.get("/api/me").json()["is_admin"] is False
        assert client.get("/api/admin/stats").json() == ADMIN_REQUIRED


def test_login_response_has_no_is_admin(setup):
    client, _ = setup
    r = client.post("/api/auth/login", json=ADMIN)
    assert "is_admin" not in r.json()


# --- admin APIs --------------------------------------------------------------

ADMIN_PATHS = ["/api/admin/stats", "/api/admin/users", "/api/admin/chats"]


@pytest.mark.parametrize("path", ADMIN_PATHS)
def test_admin_apis_need_login(setup, path):
    client, _ = setup
    r = client.get(path)
    assert r.status_code == 401
    assert r.json()["error"] == "LOGIN_REQUIRED"


@pytest.mark.parametrize("path", ADMIN_PATHS)
def test_admin_apis_reject_members(setup, path):
    client, _ = setup
    login(client, MEMBER)
    r = client.get(path)
    assert r.status_code == 403
    assert r.json() == ADMIN_REQUIRED


def test_stats_counts_users_and_todays_chats(setup):
    client, factory = setup
    start_of_day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0,
                                                       microsecond=0)
    # Member chats at 23:59 UTC yesterday and 00:00 UTC today; only the second counts.
    add_chats(factory, MEMBER["email"], 2, start=start_of_day - timedelta(minutes=1))
    add_chats(factory, ADMIN["email"], 1, start=start_of_day)
    login(client, ADMIN)
    assert client.get("/api/admin/stats").json() == {"users": 2, "chats": 3, "chats_today": 2}


def test_chats_today_uses_utc_day(factory):
    seed_admin(factory, make_settings())
    add_chats(factory, ADMIN["email"], 3, start=datetime(2026, 10, 1, 23, 58, tzinfo=timezone.utc))
    with factory() as db:
        assert count_chats_today(db, datetime(2026, 10, 1, 23, 59, tzinfo=timezone.utc)) == 2
        assert count_chats_today(db, datetime(2026, 10, 2, 0, 1, tzinfo=timezone.utc)) == 1


def test_users_list_with_chat_counts_and_paging(setup):
    client, factory = setup
    add_chats(factory, MEMBER["email"], 3)
    login(client, ADMIN)
    body = client.get("/api/admin/users").json()
    assert body["total"] == 2
    admin_row, member_row = body["items"]
    assert set(admin_row) == {"id", "email", "created_at", "chat_count", "last_chat_at"}
    assert (admin_row["email"], admin_row["chat_count"], admin_row["last_chat_at"]) == (
        ADMIN["email"], 0, None)
    assert member_row["chat_count"] == 3
    assert member_row["last_chat_at"].startswith("2026-10-01T09:02:00")
    assert "password_hash" not in json.dumps(body)

    page = client.get("/api/admin/users", params={"limit": 1, "offset": 1}).json()
    assert [item["email"] for item in page["items"]] == [MEMBER["email"]]
    assert page["total"] == 2


def test_chats_list_newest_first_with_email_and_user_filter(setup):
    client, factory = setup
    add_chats(factory, MEMBER["email"], 2)
    add_chats(factory, ADMIN["email"], 1, start=BASE_TIME + timedelta(hours=1))
    login(client, ADMIN)
    items = client.get("/api/admin/chats").json()["items"]
    assert [item["question"] for item in items] == [
        "admin@example.com q0", "member@example.com q1", "member@example.com q0"]
    assert set(items[0]) == {"id", "user_id", "email", "question", "answer", "created_at"}
    assert items[1]["email"] == MEMBER["email"]

    member_id = user_id(factory, MEMBER["email"])
    filtered = client.get("/api/admin/chats", params={"user_id": member_id, "limit": 1}).json()
    assert [item["question"] for item in filtered["items"]] == ["member@example.com q1"]
    assert client.get("/api/admin/chats", params={"user_id": 9999}).json() == {"items": []}


@pytest.mark.parametrize("path,params,field", [
    ("/api/admin/users", {"limit": 0}, "limit"),
    ("/api/admin/users", {"limit": 101}, "limit"),
    ("/api/admin/users", {"offset": -1}, "offset"),
    ("/api/admin/users", {"offset": "x"}, "offset"),
    ("/api/admin/chats", {"limit": 101}, "limit"),
    ("/api/admin/chats", {"user_id": "x"}, "user_id"),
])
def test_invalid_query_is_rejected(setup, path, params, field):
    client, _ = setup
    login(client, ADMIN)
    r = client.get(path, params=params)
    assert r.status_code == 422
    declared = client.get("/openapi.json").json()["paths"][path]["get"]["responses"]["422"]
    assert r.json() == declared["content"]["application/json"]["examples"][field]["value"]


def test_openapi_declares_admin_errors(setup):
    client, _ = setup
    paths = client.get("/openapi.json").json()["paths"]
    assert {int(c) for c in paths["/api/admin/stats"]["get"]["responses"]} == {200, 401, 403, 503}
    for path in ["/api/admin/users", "/api/admin/chats"]:
        assert {int(c) for c in paths[path]["get"]["responses"]} == {200, 401, 403, 422, 503}
    example = paths["/api/admin/stats"]["get"]["responses"]["403"]["content"]["application/json"]
    assert example["examples"]["admin_required"]["value"] == ADMIN_REQUIRED
    assert "/admin" not in paths


def test_admin_view_is_logged_without_data(setup, caplog):
    client, factory = setup
    add_chats(factory, MEMBER["email"], 1)
    login(client, ADMIN)
    with caplog.at_level(logging.INFO, logger="next_star_hunter"):
        client.get("/api/admin/chats", params={"limit": 5})
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("admin_view")]
    admin_id = user_id(factory, ADMIN["email"])
    assert len(lines) == 1
    assert lines[0].startswith(f"admin_view user_id={admin_id} path=/api/admin/chats ")
    assert "member@example.com" not in caplog.text and "q0" not in caplog.text
