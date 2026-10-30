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
    # 비어 있으면 콘솔에만 남기고, 경로가 있으면 같은 형식으로 파일에도 남긴다.
    LOG_FILE_PATH: str = ""

    # 관리자 계정. 둘 다 있으면 init_db 가 계정이 없을 때만 만든다(기존 비밀번호는 덮어쓰지 않음).
    ADMIN_EMAIL: str = ""
    ADMIN_PASSWORD: SecretStr = SecretStr("")

    # AI API. 키가 없어도 서버는 뜨고, 채팅 기능만 llm_configured()로 막는다.
    LLM_API_KEY: SecretStr = SecretStr("")
    # 수업에서 쓰는 copa(Anthropic 방식) 기준. 모델은 sonnet 고정, haiku 만 예비로 허용.
    LLM_BASE_URL: str = "https://copa.codyssey.kr/v1"
    LLM_API_STYLE: Literal["anthropic", "openai"] = "anthropic"
    LLM_MODEL: Literal["claude-sonnet-4", "claude-haiku-4"] = "claude-sonnet-4"
    LLM_TIMEOUT_SECONDS: float = Field(default=90, gt=0)
    LLM_MAX_COMPLETION_TOKENS: int = Field(default=8000, gt=0)

    def auth_configured(self) -> bool:
        return (len(self.SECRET_KEY.get_secret_value()) >= 32
                and bool(self.DATABASE_URL.get_secret_value()))

    def admin_email(self) -> str:
        """Normalized like signup emails; empty means no admin account."""
        return self.ADMIN_EMAIL.strip().casefold()

    def llm_configured(self) -> bool:
        return (bool(self.LLM_API_KEY.get_secret_value())
                and bool(self.LLM_BASE_URL) and bool(self.LLM_MODEL))
