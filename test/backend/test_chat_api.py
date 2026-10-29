"""Chat API tests with a mocked AI API (httpx.MockTransport) and in-memory SQLite."""
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import TypeAdapter
from sqlalchemy import create_engine, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.ai_client import SYSTEM_PROMPT
from app.config import Settings
from app.database import Base
from app.main import create_app
from app.models import ChatLog, User

ACCOUNT = {"email": "chat-user@example.com", "password": "chat-test-password-123"}
API_KEY = "test-llm-key-do-not-leak"
QUESTION = "밝은 분위기의 부산 출신 아이돌을 추천해줘"
ANSWER = "조건에 맞는 스타를 찾아볼게요."


def make_settings(**changes):
    values = dict(SECRET_KEY="chat-test-signing-secret-at-least-32-characters",
                  DATABASE_URL="postgresql+psycopg://unused:unused@localhost/test",
                  SESSION_HTTPS_ONLY=True, ENABLE_API_DOCS=True,
                  LLM_API_KEY=API_KEY, LLM_BASE_URL="https://llm.example.test/v1",
                  LLM_API_STYLE="anthropic", LLM_MODEL="claude-sonnet-4",
                  LLM_TIMEOUT_SECONDS=5, LLM_MAX_COMPLETION_TOKENS=512)
    values.update(changes)
    return Settings(_env_file=None, **values)


class FakeAI:
    """Records upstream requests and answers with the configured handler."""

    def __init__(self):
        self.requests = []
        self.handler = self.anthropic_ok

    def __call__(self, request):
        self.requests.append(request)
        return self.handler(request)

    @staticmethod
    def anthropic_ok(request):
        return httpx.Response(200, json={"content": [{"type": "text", "text": ANSWER}]})

    @staticmethod
    def openai_ok(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": ANSWER}}]})

    def last_body(self):
        return json.loads(self.requests[-1].content)


def build_client(fake, **changes):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    app = create_app(make_settings(**changes), factory, ai_transport=httpx.MockTransport(fake))
    return TestClient(app, base_url="https://testserver"), factory, engine


@pytest.fixture
def api():
    fake = FakeAI()
    client, factory, engine = build_client(fake)
    with client:
        client.post("/api/auth/register", json=ACCOUNT)
        client.post("/api/auth/login", json=ACCOUNT)
        yield client, factory, fake
    engine.dispose()


def test_chat_saves_question_and_answer(api):
    client, factory, fake = api
    r = client.post("/api/chat", json={"message": "  " + QUESTION + "  "})
    assert r.status_code == 200
    data = r.json()
    assert set(data) == {"id", "question", "answer", "created_at", "saved"}
    assert data["question"] == QUESTION
    assert data["answer"] == ANSWER
    assert data["saved"] is True
    assert TypeAdapter(datetime).validate_python(data["created_at"]).tzinfo is not None
    with factory() as db:
        row = db.get(ChatLog, data["id"])
        user = db.scalar(select(User))
        assert (row.user_id, row.question, row.answer) == (user.id, QUESTION, ANSWER)


def test_anthropic_request_format(api):
    client, _, fake = api
    client.post("/api/chat", json={"message": QUESTION})
    request = fake.requests[-1]
    assert str(request.url) == "https://llm.example.test/v1/messages"
    assert request.headers["x-api-key"] == API_KEY
    assert request.headers["anthropic-version"]
    body = fake.last_body()
    assert body["model"] == "claude-sonnet-4"
    assert body["max_tokens"] == 512
    assert body["system"] == SYSTEM_PROMPT
    assert body["messages"] == [{"role": "user", "content": QUESTION}]


def test_openai_request_format():
    fake = FakeAI()
    fake.handler = fake.openai_ok
    client, _, engine = build_client(fake, LLM_API_STYLE="openai",
                                     LLM_BASE_URL="https://llm.example.test/v1/")
    with client:
        client.post("/api/auth/register", json=ACCOUNT)
        client.post("/api/auth/login", json=ACCOUNT)
        r = client.post("/api/chat", json={"message": QUESTION})
    engine.dispose()
    assert r.status_code == 200
    assert r.json()["answer"] == ANSWER
    request = fake.requests[-1]
    assert str(request.url) == "https://llm.example.test/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer " + API_KEY
    body = fake.last_body()
    assert body["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert body["messages"][1:] == [{"role": "user", "content": QUESTION}]


def test_context_uses_latest_five_pairs_oldest_first(api):
    client, factory, fake = api
    base = datetime(2026, 10, 1, tzinfo=timezone.utc)
    with factory() as db:
        user_id = db.scalar(select(User)).id
        other = User(email="other@example.com", password_hash="x")
        db.add(other)
        db.flush()
        for i in range(7):
            db.add(ChatLog(user_id=user_id, question=f"q{i}", answer=f"a{i}",
                           created_at=base + timedelta(minutes=i)))
        db.add(ChatLog(user_id=other.id, question="other-q", answer="other-a",
                       created_at=base + timedelta(hours=1)))
        db.commit()
    assert client.post("/api/chat", json={"message": QUESTION}).status_code == 200
    expected = []
    for i in range(2, 7):
        expected += [{"role": "user", "content": f"q{i}"},
                     {"role": "assistant", "content": f"a{i}"}]
    expected.append({"role": "user", "content": QUESTION})
    assert fake.last_body()["messages"] == expected


def test_timeout_returns_504(api):
    client, factory, fake = api

    def slow(request):
        raise httpx.ReadTimeout("timed out", request=request)
    fake.handler = slow
    r = client.post("/api/chat", json={"message": QUESTION})
    assert r.status_code == 504
    assert r.json()["error"] == "AI_TIMEOUT"
    assert client.get("/health").status_code == 200
    with factory() as db:
        assert db.scalar(select(ChatLog)) is None


@pytest.mark.parametrize("response", [
    httpx.Response(500, text="upstream secret body"),
    httpx.Response(200, text="not json"),
    httpx.Response(200, json={"content": []}),
])
def test_upstream_failure_returns_502_without_body(api, response):
    client, _, fake = api
    fake.handler = lambda request: response
    r = client.post("/api/chat", json={"message": QUESTION})
    assert r.status_code == 502
    assert r.json() == {"error": "AI_ERROR",
                        "message": "AI 응답을 받지 못했어요. 잠시 후 다시 시도해 주세요."}
    assert "upstream secret body" not in r.text


def test_connection_error_returns_502(api):
    client, _, fake = api

    def down(request):
        raise httpx.ConnectError("connection refused", request=request)
    fake.handler = down
    assert client.post("/api/chat", json={"message": QUESTION}).json()["error"] == "AI_ERROR"


def test_not_configured_returns_503_without_calling_ai():
    fake = FakeAI()
    client, _, engine = build_client(fake, LLM_API_KEY="")
    with client:
        client.post("/api/auth/register", json=ACCOUNT)
        client.post("/api/auth/login", json=ACCOUNT)
        r = client.post("/api/chat", json={"message": QUESTION})
    engine.dispose()
    assert r.status_code == 503
    assert r.json()["error"] == "AI_NOT_CONFIGURED"
    assert fake.requests == []


def test_login_required():
    fake = FakeAI()
    client, _, engine = build_client(fake)
    with client:
        r = client.post("/api/chat", json={"message": QUESTION})
    engine.dispose()
    assert r.status_code == 401
    assert r.json()["error"] == "LOGIN_REQUIRED"
    assert fake.requests == []


@pytest.mark.parametrize("body", [
    {"message": ""}, {"message": "   "}, {"message": "가" * 1001}, {},
    {"message": QUESTION, "extra": "x"}, {"message": 123},
])
def test_invalid_message_is_rejected(api, body):
    client, _, fake = api
    r = client.post("/api/chat", json=body)
    assert r.status_code == 422
    assert r.json()["error"] == "VALIDATION_ERROR"
    assert fake.requests == []


def test_message_length_limit_counts_after_strip(api):
    client, _, _ = api
    r = client.post("/api/chat", json={"message": " " + "가" * 1000 + " "})
    assert r.status_code == 200


def test_db_save_failure_still_returns_answer(api, monkeypatch, caplog):
    client, factory, _ = api

    def broken_commit(*args, **kwargs):
        raise OperationalError("private SQL", {}, Exception("password=must-not-appear"))
    monkeypatch.setattr(factory.class_, "commit", broken_commit)
    with caplog.at_level("INFO", logger="next_star_hunter"):
        r = client.post("/api/chat", json={"message": QUESTION})
    assert r.status_code == 200
    data = r.json()
    assert data["saved"] is False
    assert data["id"] is None
    assert data["answer"] == ANSWER
    assert "db_save_failure" in caplog.text
    assert "OperationalError" in caplog.text
    assert "must-not-appear" not in caplog.text + r.text


def test_logs_have_events_but_no_text_or_key(api, caplog):
    client, _, fake = api
    with caplog.at_level("INFO", logger="next_star_hunter"):
        client.post("/api/chat", json={"message": QUESTION})
        fake.handler = lambda request: httpx.Response(500, text="upstream secret body")
        client.post("/api/chat", json={"message": QUESTION})
    for event in ["request_received", "ai_call_start", "ai_call_success",
                  "db_save_success", "ai_call_failure"]:
        assert event in caplog.text
    for secret in [QUESTION, ANSWER, API_KEY, "upstream secret body"]:
        assert secret not in caplog.text


def test_openapi_declares_chat_errors(api):
    client, _, _ = api
    schema = client.get("/openapi.json").json()
    assert "HTTPValidationError" not in json.dumps(schema)
    responses = schema["paths"]["/api/chat"]["post"]["responses"]
    assert {int(code) for code in responses} == {200, 401, 403, 422, 502, 503, 504}
    declared = responses["422"]["content"]["application/json"]
    assert declared["schema"]["$ref"] == "#/components/schemas/ValidationErrorResponse"
    r = client.post("/api/chat", json={"message": ""})
    assert r.json() == declared["examples"]["message"]["value"]
