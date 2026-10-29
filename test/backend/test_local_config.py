"""Local env precedence and safe readiness diagnostics."""
import importlib.util
from pathlib import Path

from app.config import Settings

CHECK_LOCAL = Path(__file__).resolve().parents[2] / "backend" / "check_local.py"
spec = importlib.util.spec_from_file_location("check_local", CHECK_LOCAL)
check_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_module)


def test_default_files_keep_root_env_precedence():
    paths = Settings.model_config["env_file"]
    assert paths[0].parts[-2:] == ("backend", ".env")
    assert paths[1].name == ".env" and paths[1].parent != paths[0].parent


def test_backend_env_fallback_and_root_override(tmp_path, monkeypatch):
    for key in ["SECRET_KEY", "DATABASE_URL"]:
        monkeypatch.delenv(key, raising=False)
    backend = tmp_path / "backend.env"
    root = tmp_path / "root.env"
    backend.write_text("SECRET_KEY=backend-development-secret-at-least-32-characters\n",
                       encoding="utf-8")
    assert Settings(_env_file=(backend, root)).SECRET_KEY.get_secret_value().startswith("backend")
    root.write_text("SECRET_KEY=root-development-secret-at-least-32-characters\n", encoding="utf-8")
    assert Settings(_env_file=(backend, root)).SECRET_KEY.get_secret_value().startswith("root")
    monkeypatch.setenv("SECRET_KEY", "environment-secret-at-least-32-characters")
    settings = Settings(_env_file=(backend, root))
    assert settings.SECRET_KEY.get_secret_value().startswith("environment")


def test_readiness_reports_missing_names_not_values():
    result = check_module.check_local(Settings(_env_file=None, SECRET_KEY="short", DATABASE_URL=""))
    assert not result["ready"] and result["error"] == "AUTH_NOT_CONFIGURED"
    assert "short" not in str(result)


def test_readiness_hides_connection_details(monkeypatch):
    secret = "private-database-password"
    def fail(*args, **kwargs):
        raise RuntimeError(secret)
    monkeypatch.setattr(check_module, "build_engine", fail)
    settings = Settings(_env_file=None, SECRET_KEY="test-signing-secret-at-least-32-characters",
                        DATABASE_URL="postgresql://u:" + secret + "@localhost/db")
    result = check_module.check_local(settings)
    assert result == {"ready": False, "error": "DB_UNAVAILABLE", "error_type": "RuntimeError"}
    assert secret not in str(result)
