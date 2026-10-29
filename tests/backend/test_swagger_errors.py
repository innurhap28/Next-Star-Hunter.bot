"""Verify Swagger examples against actual account error responses."""
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.database import Base
from app.main import create_app
from app.models import User
from app.schemas import ErrorResponse, ValidationErrorResponse

ACCOUNT = {"email": "swagger-errors@example.com", "password": "valid-test-password-123"}
OPERATIONS = [("/api/auth/register", "post"), ("/api/auth/login", "post"),
              ("/api/auth/logout", "post"), ("/api/me", "get")]


def settings(**changes):
    values = dict(SECRET_KEY="swagger-test-signing-key-at-least-32-characters",
                  DATABASE_URL="postgresql+psycopg://unused:unused@localhost/test",
                  ENABLE_API_DOCS=True, SESSION_HTTPS_ONLY=True)
    values.update(changes)
    return Settings(_env_file=None, **values)


@pytest.fixture
def api():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with TestClient(create_app(settings(), factory), base_url="https://testserver") as client:
        yield client, factory
    engine.dispose()


def check_error(client, path, method, response, status, example):
    assert response.status_code == status
    operation = client.get("/openapi.json").json()["paths"][path][method]
    declared = operation["responses"][str(status)]["content"]["application/json"]
    assert response.json() == declared["examples"][example]["value"]
    model = ValidationErrorResponse if status == 422 else ErrorResponse
    model.model_validate(response.json())
    assert "detail" not in response.json()
    assert ACCOUNT["password"] not in response.text


def test_openapi_replaces_default_validation_error_schema(api):
    client, _ = api
    schema = client.get("/openapi.json").json()
    assert "HTTPValidationError" not in json.dumps(schema)
    for path in ["/api/auth/register", "/api/auth/login"]:
        declared = schema["paths"][path]["post"]["responses"]["422"]["content"]["application/json"]
        assert declared["schema"]["$ref"] == "#/components/schemas/ValidationErrorResponse"
    validation = schema["components"]["schemas"]["ValidationErrorResponse"]
    assert set(validation["required"]) == {"error", "message", "fields"}
    assert "detail" not in validation["properties"]
    assert schema["components"]["schemas"]["ErrorResponse"]["additionalProperties"] is False


@pytest.mark.parametrize("path,method,codes", [
    ("/api/auth/register", "post", {201,403,409,422,503}),
    ("/api/auth/login", "post", {200,401,403,422,503}),
    ("/api/auth/logout", "post", {204,401,403,503}),
    ("/api/me", "get", {200,401,503}),
])
def test_documented_statuses_and_examples_validate(api, path, method, codes):
    client, _ = api
    operation = client.get("/openapi.json").json()["paths"][path][method]
    assert {int(code) for code in operation["responses"]} == codes
    for code, response in operation["responses"].items():
        if int(code) < 400:
            continue
        content = response["content"]["application/json"]
        model = ValidationErrorResponse if code == "422" else ErrorResponse
        for example in content["examples"].values():
            model.model_validate(example["value"])
            forbidden = {"detail", "input", "ctx", "password", "password_hash"}
            assert not (forbidden & example["value"].keys())


@pytest.mark.parametrize("path", ["/api/auth/register", "/api/auth/login"])
@pytest.mark.parametrize("field,value", [("password", "short"), ("email", "invalid-email")])
def test_field_error_matches_swagger_example(api, path, field, value):
    client, _ = api
    response = client.post(path, json={**ACCOUNT, field:value})
    check_error(client, path, "post", response, 422, field)
    assert value not in response.text


@pytest.mark.parametrize("path", ["/api/auth/register", "/api/auth/login"])
def test_invalid_json_integer_location_matches_swagger(api, path):
    client, _ = api
    response = client.post(path, content="{", headers={"Content-Type":"application/json"})
    check_error(client, path, "post", response, 422, "invalid_json")
    assert type(response.json()["fields"][0][1]) is int


def test_login_failure_matches_swagger(api):
    client, _ = api
    response = client.post("/api/auth/login", json=ACCOUNT)
    check_error(client, "/api/auth/login", "post", response, 401, "invalid_credentials")


@pytest.mark.parametrize("path,method", [("/api/me","get"),("/api/auth/logout","post")])
def test_login_required_matches_swagger(api, path, method):
    client, _ = api
    check_error(client, path, method, client.request(method, path), 401, "login_required")


@pytest.mark.parametrize("path,method", [("/api/me","get"),("/api/auth/logout","post")])
def test_deleted_session_user_matches_swagger(api, path, method):
    client, factory = api
    created = client.post("/api/auth/register", json=ACCOUNT).json()
    assert client.post("/api/auth/login", json=ACCOUNT).status_code == 200
    with factory() as db:
        db.delete(db.get(User, created["id"]))
        db.commit()
    check_error(client, path, method, client.request(method, path), 401, "stale_session")


def test_duplicate_email_matches_swagger(api):
    client, _ = api
    assert client.post("/api/auth/register", json=ACCOUNT).status_code == 201
    check_error(client, "/api/auth/register", "post",
                client.post("/api/auth/register", json=ACCOUNT), 409, "email_exists")


@pytest.mark.parametrize("path", ["/api/auth/register", "/api/auth/login", "/api/auth/logout"])
def test_origin_failure_matches_swagger(api, path):
    client, _ = api
    response = client.post(path, json=ACCOUNT, headers={"Origin":"https://untrusted.example"})
    check_error(client, path, "post", response, 403, "origin_not_allowed")


@pytest.mark.parametrize("path,method", OPERATIONS)
@pytest.mark.parametrize("configured,example",
                         [(False, "auth_not_configured"), (True, "db_not_configured")])
def test_configuration_errors_match_swagger(path, method, configured, example):
    if configured:
        config = settings(DATABASE_URL="sqlite://")
    else:
        config = settings(SECRET_KEY="", DATABASE_URL="")
    with TestClient(create_app(config), base_url="https://testserver") as client:
        if method == "post":
            response = client.request(method, path, json=ACCOUNT)
        else:
            response = client.get(path)
        check_error(client, path, method, response, 503, example)


@pytest.mark.parametrize("path,method", OPERATIONS)
def test_db_failure_matches_swagger_without_leaking_details(api, monkeypatch, path, method):
    client, factory = api
    if path in {"/api/me", "/api/auth/logout"}:
        client.post("/api/auth/register", json=ACCOUNT)
        client.post("/api/auth/login", json=ACCOUNT)
    def unavailable(*args, **kwargs):
        raise OperationalError("private SQL", {}, Exception("password=must-not-appear"))
    monkeypatch.setattr(factory.class_, "scalar", unavailable)
    monkeypatch.setattr(factory.class_, "get", unavailable)
    response = client.request(method, path, json=ACCOUNT) if method == "post" else client.get(path)
    check_error(client, path, method, response, 503, "db_unavailable")
    assert "must-not-appear" not in response.text


def test_swagger_stays_optional_and_health_contract_is_unchanged():
    with TestClient(create_app(settings(ENABLE_API_DOCS=False))) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
        assert client.get("/health").json() == {"status":"ok","service":"next-star-hunter"}
