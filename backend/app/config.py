"""Settings for the new Next Star Hunter service."""
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT_DIR / "backend" / ".env", ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )
    SECRET_KEY: SecretStr = SecretStr("")
    DATABASE_URL: SecretStr = SecretStr("")
    SESSION_HTTPS_ONLY: bool = False
    ENABLE_API_DOCS: bool = False

    def auth_configured(self) -> bool:
        return (len(self.SECRET_KEY.get_secret_value()) >= 32
                and bool(self.DATABASE_URL.get_secret_value()))
