"""Logging setup: console output for every run, plus an optional log file.

LOG_FILE_PATH adds a file handler to the "next_star_hunter" logger with the
same format. A path that cannot be opened only logs a warning; the server
still starts and keeps logging to the console.
"""
import logging
from pathlib import Path

LOGGER_NAME = "next_star_hunter"
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
# Marks the handler this module added, so a second create_app() replaces it.
_HANDLER_FLAG = "_next_star_file_handler"

logger = logging.getLogger(LOGGER_NAME)


def setup_console_logging():
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)


def setup_file_logging(path):
    """Write the app logger to `path` as well. Returns the handler, or None."""
    for handler in list(logger.handlers):
        if getattr(handler, _HANDLER_FLAG, False):
            logger.removeHandler(handler)
            handler.close()
    if not path:
        return None
    try:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(target, encoding="utf-8")
    except OSError as error:
        logger.warning("log_file_open_failure path=%s error_type=%s",
                       path, type(error).__name__)
        return None
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    setattr(handler, _HANDLER_FLAG, True)
    logger.addHandler(handler)
    return handler
