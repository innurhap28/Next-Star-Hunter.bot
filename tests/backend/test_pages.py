"""Page routes: session redirects, template rendering and static files."""
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.database import Base
from app.init_db import seed_admin
from app.main import create_app

ACCOUNT = {"email": "page@example.com", "password": "safe-test-password-123"}

@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        _env_file=None,
        SECRET_KEY="test-only-signing-secret-at-least-32-characters",
        DATABASE_URL="postgresql+psycopg://unused:unused@localhost/test",
    )
    with TestClient(create_app(settings, factory), follow_redirects=False) as client:
        yield client
    engine.dispose()

ADMIN_PASSWORD = "admin-test-password-123"


def log_in(client):
    assert client.post("/api/auth/register", json=ACCOUNT).status_code == 201
    assert client.post("/api/auth/login", json=ACCOUNT).status_code == 200

def test_chat_page_redirects_to_auth_when_logged_out(client):
    r = client.get("/")
    assert r.status_code == 303
    assert r.headers["location"] == "/auth"

def test_chat_page_renders_when_logged_in(client):
    log_in(client)
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "/static/css/app.css" in r.text
    assert "/static/js/chat.js" in r.text

def test_auth_page_renders_when_logged_out(client):
    r = client.get("/auth")
    assert r.status_code == 200
    assert "/static/js/auth.js" in r.text

def test_auth_page_has_password_confirm_and_source_footer(client):
    html = client.get("/auth").text
    assert 'id="signup-password-confirm"' in html
    assert "스타 정보 출처" in html
    assert "CC BY-NC-SA 2.0 KR" in html

def test_auth_page_redirects_home_when_logged_in(client):
    log_in(client)
    r = client.get("/auth")
    assert r.status_code == 303
    assert r.headers["location"] == "/"

def test_pages_have_no_leftover_template_syntax(client):
    page = client.get("/auth").text
    log_in(client)
    for html in (page, client.get("/").text):
        assert not re.search(r"\{\{|\}\}|\{%|%\}", html)
        assert "../static" not in html

def test_static_files_are_served(client):
    css = client.get("/static/css/app.css")
    assert css.status_code == 200
    assert css.headers["content-type"].startswith("text/css")
    assert client.get("/static/js/chat.js").status_code == 200
    assert client.get("/static/js/missing.js").status_code == 404

def test_pages_are_hidden_from_openapi(client):
    paths = client.app.openapi()["paths"]
    assert "/" not in paths and "/auth" not in paths


def test_pages_preconnect_and_preload_fonts(client):
    page = client.get("/auth").text
    log_in(client)
    for html in (page, client.get("/").text):
        assert 'rel="preconnect" href="https://fonts.googleapis.com"' in html
        assert 'rel="preconnect" href="https://fonts.gstatic.com" crossorigin' in html
        assert 'rel="preload" as="style" href="https://fonts.googleapis.com/css2' in html
        assert html.index("preload") < html.index("/static/css/app.css")


def test_app_css_has_no_font_import(client):
    css = client.get("/static/css/app.css").text
    assert "@import" not in css


@pytest.fixture
def admin_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        _env_file=None,
        SECRET_KEY="test-only-signing-secret-at-least-32-characters",
        DATABASE_URL="postgresql+psycopg://unused:unused@localhost/test",
        ADMIN_EMAIL="Admin@Example.com",
        ADMIN_PASSWORD=ADMIN_PASSWORD,
    )
    assert seed_admin(factory, settings) == "created"
    with TestClient(create_app(settings, factory), follow_redirects=False) as client:
        yield client
    engine.dispose()


def log_in_as(client, email):
    account = {"email": email, "password": "safe-test-password-123"}
    assert client.post("/api/auth/register", json=account).status_code == 201
    assert client.post("/api/auth/login", json=account).status_code == 200


def log_in_admin(client):
    # 관리자 계정은 회원가입이 막혀 있고 init_db(seed_admin)로만 만들어진다.
    account = {"email": "admin@example.com", "password": ADMIN_PASSWORD}
    assert client.post("/api/auth/login", json=account).status_code == 200


def test_admin_page_redirects_to_auth_when_logged_out(admin_client):
    r = admin_client.get("/admin")
    assert r.status_code == 303
    assert r.headers["location"] == "/auth"


def test_admin_page_redirects_home_for_normal_user(admin_client):
    log_in_as(admin_client, "user@example.com")
    r = admin_client.get("/admin")
    assert r.status_code == 303
    assert r.headers["location"] == "/"


def test_admin_page_renders_for_admin_email(admin_client):
    log_in_admin(admin_client)
    r = admin_client.get("/admin")
    assert r.status_code == 200
    assert "/static/js/admin.js" in r.text
    assert 'rel="preload" as="style"' in r.text
    assert not re.search(r"\{\{|\}\}|\{%|%\}", r.text)


def test_admin_page_redirects_when_session_replaced(admin_client):
    log_in_admin(admin_client)
    old_cookie = admin_client.cookies.get("next_star_session")
    account = {"email": "admin@example.com", "password": ADMIN_PASSWORD}
    assert admin_client.post("/api/auth/login", json=account).status_code == 200
    admin_client.cookies.set("next_star_session", old_cookie)
    r = admin_client.get("/admin")
    assert r.status_code == 303
    assert r.headers["location"] == "/auth?reason=session_replaced"


def test_admin_page_closed_without_admin_email(client):
    log_in(client)
    r = client.get("/admin")
    assert r.status_code == 303
    assert r.headers["location"] == "/"
    assert "/admin" not in client.app.openapi()["paths"]


def test_chat_page_has_account_menu_resizer_and_source_footer(client):
    log_in(client)
    html = client.get("/").text
    assert 'aria-haspopup="menu"' in html and 'aria-controls="user-menu"' in html
    assert 'href="/admin" hidden data-admin-link' in html
    assert "data-menu-logout" in html
    assert 'role="separator"' in html
    assert 'aria-valuemin="200"' in html and 'aria-valuemax="480"' in html
    assert "스타 정보 출처:" in html
    assert 'href="https://namu.wiki/"' in html
    assert 'href="https://creativecommons.org/licenses/by-nc-sa/2.0/kr/"' in html


def test_chat_assets_have_scroll_regions_and_loading_indicator(client):
    css = client.get("/static/css/app.css").text
    js = client.get("/static/js/chat.js").text
    # 페이지는 고정하고 대화 목록·메시지 영역만 스크롤한다.
    assert "body.chat-page" in css and "overflow: hidden" in css
    assert ".loading-spinner" in css and "@keyframes loading-spin" in css
    assert "prefers-reduced-motion" in css
    assert "scrollRestoration" in js and "const scrollToBottom" in js
    assert "답변을 준비하고 있어요…" in js
    assert "nsh.sidebarOpen" in js


def test_chat_assets_use_conversation_list(client):
    log_in(client)
    html = client.get("/").text
    js = client.get("/static/js/chat.js").text
    css = client.get("/static/css/app.css").text
    assert "data-chat-history" in html and "data-new-chat" in html
    # 최근 대화는 대화방 목록이고, 질문은 지금 연 대화방 id 와 함께 보낸다.
    assert "/api/me/conversations?limit=" in js
    assert "/chats`" in js and 'method: "DELETE"' in js
    assert "conversation_id: state.currentId" in js
    assert "CONVERSATION_NOT_FOUND" in js
    assert "nsh.lastConversation" in js
    # 질문 하나씩 보여 주던 옛 목록과 /api/me/chats 연결은 화면에서 뺐다.
    assert "/api/me/chats" not in js
    assert ".history-entry.is-current" in css and ".history-time" in css
