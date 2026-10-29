"""LOG_FILE_PATH: the app logger also writes to a file, and a bad path never stops startup."""
import logging

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.logging_config import LOGGER_NAME, setup_file_logging
from app.main import create_app


def file_handlers():
    return [h for h in logging.getLogger(LOGGER_NAME).handlers
            if isinstance(h, logging.FileHandler)]


@pytest.fixture(autouse=True)
def no_file_handler():
    setup_file_logging("")
    yield
    setup_file_logging("")


def test_log_file_path_writes_app_logs_to_file(tmp_path, caplog):
    path = tmp_path / "logs" / "nested" / "app.log"
    client = TestClient(create_app(Settings(_env_file=None, LOG_FILE_PATH=str(path))))
    # The server sets INFO with basicConfig; pytest's own root handler hides that here.
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        assert client.get("/health").status_code == 200
    for handler in file_handlers():
        handler.flush()
    text = path.read_text(encoding="utf-8")
    assert "INFO next_star_hunter request_received method=GET path=/health" in text


def test_no_file_handler_without_log_file_path():
    create_app(Settings(_env_file=None))
    assert file_handlers() == []


def test_second_app_replaces_the_file_handler(tmp_path):
    create_app(Settings(_env_file=None, LOG_FILE_PATH=str(tmp_path / "a.log")))
    create_app(Settings(_env_file=None, LOG_FILE_PATH=str(tmp_path / "b.log")))
    handlers = file_handlers()
    assert len(handlers) == 1
    assert handlers[0].baseFilename == str(tmp_path / "b.log")


def test_unopenable_log_file_only_warns(tmp_path, caplog):
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("", encoding="utf-8")
    bad_path = blocker / "app.log"
    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        client = TestClient(create_app(Settings(_env_file=None, LOG_FILE_PATH=str(bad_path))))
    assert client.get("/health").status_code == 200
    assert "log_file_open_failure" in caplog.text
    assert file_handlers() == []
