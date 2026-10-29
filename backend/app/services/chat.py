"""Chat flow: recent context, star search, AI call, source line, and log saving.

HTTP concerns stay in routers/chat.py. AIError from the AI call is raised as is
so the router can map it to an HTTP response.
"""
import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..crud.chat_logs import recent_chat_pairs, save_chat_log
from ..models import utc_now
from .ai_client import AIError, ask_ai
from .star_search import (
    StarSearchResult,
    format_reference,
    remove_source_lines,
    search_stars,
    source_line,
)

logger = logging.getLogger("next_star_hunter")
CONTEXT_PAIRS = 5

__all__ = ["AIError", "CONTEXT_PAIRS", "ChatResult", "answer_question"]


@dataclass
class ChatResult:
    # saved is False (id None) when the answer was made but the DB save failed.
    id: Optional[int]
    question: str
    answer: str
    created_at: datetime
    saved: bool


def answer_question(db: Session, settings, user_id: int, message: str, *,
                    request_id: str, transport=None) -> ChatResult:
    """Answer one question and save it. Raises AIError when the AI call fails."""
    history = recent_chat_pairs(db, user_id, CONTEXT_PAIRS)
    previous = history[-1].question if history else None
    # Star data lookup never raises; with no data the AI answers without references.
    found = StarSearchResult()
    if settings.llm_configured():
        found = search_stars(db.get_bind(), message, previous, request_id=request_id)
    # Message text and answers are never logged; only ids, timing, and error codes.
    logger.info("ai_call_start user_id=%s request_id=%s", user_id, request_id)
    started = time.monotonic()
    try:
        answer = ask_ai(settings, history, message, transport=transport,
                        references=format_reference(found))
    except AIError as error:
        logger.warning("ai_call_failure request_id=%s error=%s reason=%s",
                       request_id, error.code, error.reason)
        raise
    latency_ms = int((time.monotonic() - started) * 1000)
    logger.info("ai_call_success request_id=%s latency_ms=%s", request_id, latency_ms)
    credit = source_line(found)
    if credit:
        # The model may copy a source line from the history; the server adds the only one.
        answer = remove_source_lines(answer) + "\n\n" + credit

    created_at = utc_now()
    try:
        log = save_chat_log(db, user_id, message, answer, created_at)
    except SQLAlchemyError as error:
        # The answer is already made, so return it and tell the client it was not saved.
        logger.error("db_save_failure user_id=%s request_id=%s error_type=%s",
                     user_id, request_id, type(error).__name__)
        return ChatResult(id=None, question=message, answer=answer,
                          created_at=created_at, saved=False)
    logger.info("db_save_success user_id=%s chat_id=%s request_id=%s",
                user_id, log.id, request_id)
    return ChatResult(id=log.id, question=log.question, answer=log.answer,
                      created_at=log.created_at, saved=True)
