"""Page routes: session redirects, template rendering and static files."""
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.database import Base
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
