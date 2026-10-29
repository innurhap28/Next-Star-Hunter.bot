"""Local setup must never overwrite another database's credentials or data."""
from pathlib import Path
import importlib.util
import pytest
from dotenv import dotenv_values
from sqlalchemy import make_url

spec = importlib.util.spec_from_file_location("local_postgres", Path(__file__).resolve().parents[2] / "backend" / "local_postgres.py")
local = importlib.util.module_from_spec(spec)
spec.loader.exec_module(local)


def state():
    return {"user":"test-user", "password":"test-password", "port":55432,
            "signing_key":"test-signing-key-at-least-32-characters"}


def test_setup_writes_backend_env_without_printing_secret(tmp_path, monkeypatch, capsys):
    path = tmp_path / ".env"
    monkeypatch.setattr(local, "ENV_FILE", path)
    local.write_local_env(state())
    values = dotenv_values(path)
    assert values["SECRET_KEY"] == state()["signing_key"]
    assert make_url(values["DATABASE_URL"]).get_backend_name() == "postgresql"
    assert values["ENABLE_API_DOCS"] == "true"
    assert capsys.readouterr().out == ""


def test_setup_does_not_overwrite_another_db_config(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    original = "DATABASE_URL=postgresql://another-host/database\n"
    path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(local, "ENV_FILE", path)
    with pytest.raises(local.SetupError, match="not changed"):
        local.write_local_env(state())
    assert path.read_text(encoding="utf-8") == original


def test_missing_runtime_does_not_create_credentials(tmp_path, monkeypatch):
    monkeypatch.setattr(local, "BIN", tmp_path / "no-binaries")
    with pytest.raises(local.SetupError, match="binaries are missing"):
        local.setup_database()
    assert not list(tmp_path.iterdir())
