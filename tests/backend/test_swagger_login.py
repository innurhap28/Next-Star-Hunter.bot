"""Swagger "Try it out" login: request examples and local address origin check."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.database import Base
from app.main import create_app
from app.schemas import Credentials

ACCOUNT = {"email": "swagger-login@example.com", "password": "valid-test-password-123"}


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    settings = Settings(_env_file=None,
                        SECRET_KEY="swagger-login-signing-key-at-least-32-characters",
                        DATABASE_URL="postgresql+psycopg://unused:unused@localhost/test",
                        ENABLE_API_DOCS=True, SESSION_HTTPS_ONLY=False)
    with TestClient(create_app(settings, factory), base_url="http://127.0.0.1:8001") as client:
        yield client
    engine.dispose()


def post(client, path, host, origin=None):
    # Host is set directly so IPv6 addresses work with every TestClient version.
    headers = {"Host": host}
    if origin is not None:
        headers["Origin"] = origin
    return client.post(path, json=ACCOUNT, headers=headers)


def swagger_example(client):
    schema = client.get("/openapi.json").json()["components"]["schemas"]["Credentials"]
    return {name: prop["examples"][0] for name, prop in schema["properties"].items()}


def test_openapi_shows_valid_request_examples(client):
    example = swagger_example(client)
    assert example == {"email": "user@example.com", "password": "password1234"}
    Credentials.model_validate(example)


def test_swagger_example_payload_registers_and_logs_in(client):
    example = swagger_example(client)
    assert client.post("/api/auth/register", json=example).status_code == 201
    response = client.post("/api/auth/login", json=example)
    assert response.status_code == 200
    assert response.json()["email"] == example["email"]


@pytest.mark.parametrize("host,origin", [
    ("127.0.0.1:8001", "http://localhost:8001"),
    ("localhost:8001", "http://127.0.0.1:8001"),
    ("[::1]:8001", "http://localhost:8001"),
    ("localhost:8001", "http://[::1]:8001"),
    ("LOCALHOST:8001", "http://127.0.0.1:8001"),
    ("localhost", "http://127.0.0.1"),
    ("localhost", "http://127.0.0.1:80"),
])
def test_local_addresses_on_same_port_are_same_origin(client, host, origin):
    assert post(client, "/api/auth/register", host, origin).status_code == 201
    assert post(client, "/api/auth/login", host, origin).status_code == 200


@pytest.mark.parametrize("host,origin", [
    ("127.0.0.1:8001", "https://untrusted.example"),
    ("127.0.0.1:8001", "http://localhost:3000"),
    ("127.0.0.1:8001", "https://localhost:8001"),
    ("127.0.0.1:8001", "http://localhost.untrusted.example:8001"),
    ("127.0.0.1:8001", "http://127.0.0.2:8001"),
    ("127.0.0.1:8001", "null"),
    ("127.0.0.1:8001", "http://["),
    ("[::1]:8001", "http://[::2]:8001"),
    ("app.example:8001", "http://localhost:8001"),
    ("app.example", "http://127.0.0.1"),
])
def test_other_origins_are_still_blocked(client, host, origin):
    for path in ["/api/auth/register", "/api/auth/login"]:
        response = post(client, path, host, origin)
        assert response.status_code == 403
        assert response.json()["error"] == "ORIGIN_NOT_ALLOWED"


def test_requests_without_origin_are_still_allowed(client):
    assert post(client, "/api/auth/register", "localhost:8001").status_code == 201
    assert post(client, "/api/auth/login", "localhost:8001").status_code == 200
