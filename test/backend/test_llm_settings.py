"""AI API and log settings read from the environment."""
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app

LLM_KEYS = ["LLM_API_KEY", "LLM_BASE_URL", "LLM_API_STYLE", "LLM_MODEL",
            "LLM_TIMEOUT_SECONDS", "LLM_MAX_COMPLETION_TOKENS", "LLM_JSON_MODE",
            "CHAT_TOTAL_TIMEOUT_SECONDS", "KNOWLEDGE_USAGE_SCOPE", "LOG_FILE_PATH"]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in LLM_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_defaults_without_llm_env():
    settings = Settings(_env_file=None)
    assert settings.LLM_API_STYLE == "anthropic"
    assert settings.LLM_BASE_URL == "https://copa.codyssey.kr/v1"
    assert settings.LLM_MODEL == "claude-sonnet-4"
    assert settings.LLM_TIMEOUT_SECONDS == 90
    assert settings.LLM_MAX_COMPLETION_TOKENS == 8000
    assert settings.LLM_JSON_MODE is False
    assert settings.CHAT_TOTAL_TIMEOUT_SECONDS == 105
    assert settings.KNOWLEDGE_USAGE_SCOPE == "educational_noncommercial"
    assert settings.LOG_FILE_PATH == ""
    assert not settings.llm_configured()


def test_reads_llm_values_from_env(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "test-llm-key-value")
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example.test/v1")
    monkeypatch.setenv("LLM_API_STYLE", "openai")
    monkeypatch.setenv("LLM_MODEL", "claude-haiku-4")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "30.5")
    monkeypatch.setenv("LLM_MAX_COMPLETION_TOKENS", "1024")
    monkeypatch.setenv("LLM_JSON_MODE", "true")
    monkeypatch.setenv("KNOWLEDGE_USAGE_SCOPE", "commercial")
    monkeypatch.setenv("LOG_FILE_PATH", "/data/logs/app.log")
    settings = Settings(_env_file=None)
    assert settings.LLM_API_KEY.get_secret_value() == "test-llm-key-value"
    assert settings.LLM_API_STYLE == "openai"
    assert settings.LLM_MODEL == "claude-haiku-4"
    assert settings.LLM_TIMEOUT_SECONDS == 30.5
    assert settings.LLM_MAX_COMPLETION_TOKENS == 1024
    assert settings.LLM_JSON_MODE is True
    assert settings.KNOWLEDGE_USAGE_SCOPE == "commercial"
    assert settings.LOG_FILE_PATH == "/data/logs/app.log"
    assert settings.llm_configured()


def test_empty_values_from_env_example_use_defaults(tmp_path):
    env = tmp_path / ".env"
    env.write_text("LLM_API_KEY=\nLLM_TIMEOUT_SECONDS=\nLOG_FILE_PATH=\n", encoding="utf-8")
    settings = Settings(_env_file=env)
    assert settings.LLM_TIMEOUT_SECONDS == 90
    assert not settings.llm_configured()


@pytest.mark.parametrize("key, value", [
    ("LLM_API_STYLE", "gemini"),
    ("LLM_MODEL", "claude-opus-4-8"),
    ("LLM_MODEL", "gpt-5.4"),
    ("LLM_TIMEOUT_SECONDS", "0"),
    ("LLM_TIMEOUT_SECONDS", "-5"),
    ("LLM_MAX_COMPLETION_TOKENS", "0"),
    ("CHAT_TOTAL_TIMEOUT_SECONDS", "0"),
    ("KNOWLEDGE_USAGE_SCOPE", "all"),
])
def test_invalid_values_are_rejected(monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_llm_configured_needs_key_and_url():
    base = {"LLM_API_KEY": "k", "LLM_BASE_URL": "https://llm.example.test"}
    assert Settings(_env_file=None, **base).llm_configured()
    for missing in base:
        values = dict(base, **{missing: ""})
        assert not Settings(_env_file=None, **values).llm_configured()


def test_only_api_key_is_needed_for_copa():
    assert Settings(_env_file=None, LLM_API_KEY="k").llm_configured()


def test_api_key_is_hidden_in_repr():
    settings = Settings(_env_file=None, LLM_API_KEY="do-not-show-this-key")
    assert "do-not-show-this-key" not in repr(settings)
    assert "do-not-show-this-key" not in str(settings.model_dump())


def test_health_works_without_llm_settings():
    client = TestClient(create_app(Settings(_env_file=None)))
    response = client.get("/health")
    assert response.status_code == 200
