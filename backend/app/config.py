"""Settings for the new Next Star Hunter service."""
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT_DIR / "backend" / ".env", ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )
    SECRET_KEY: SecretStr = SecretStr("")
    DATABASE_URL: SecretStr = SecretStr("")
    SESSION_HTTPS_ONLY: bool = False
    ENABLE_API_DOCS: bool = False
    LOG_FILE_PATH: str = ""

    # AI API. 키가 없어도 서버는 뜨고, 채팅 기능만 llm_configured()로 막는다.
    LLM_API_KEY: SecretStr = SecretStr("")
    LLM_BASE_URL: str = ""
    LLM_API_STYLE: Literal["anthropic", "openai"] = "anthropic"
    LLM_MODEL: str = ""
    LLM_TIMEOUT_SECONDS: float = Field(default=90, gt=0)
    LLM_MAX_COMPLETION_TOKENS: int = Field(default=8000, gt=0)
    LLM_JSON_MODE: bool = False
    CHAT_TOTAL_TIMEOUT_SECONDS: float = Field(default=105, gt=0)
    KNOWLEDGE_USAGE_SCOPE: Literal["educational_noncommercial", "commercial"] = (
        "educational_noncommercial")

    def auth_configured(self) -> bool:
        return (len(self.SECRET_KEY.get_secret_value()) >= 32
                and bool(self.DATABASE_URL.get_secret_value()))

    def llm_configured(self) -> bool:
        return (bool(self.LLM_API_KEY.get_secret_value())
                and bool(self.LLM_BASE_URL) and bool(self.LLM_MODEL))
