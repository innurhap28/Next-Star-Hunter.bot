"""Chat flow: recent context, star search, AI call, source line, and log saving.

HTTP concerns stay in routers/chat.py. AIError from the AI call is raised as is
so the router can map it to an HTTP response.
"""
import logging
import random
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
    remove_title_lines,
    search_stars,
    source_line,
    title_line,
)

logger = logging.getLogger("next_star_hunter")
CONTEXT_PAIRS = 5
# Picks the one star to recommend. Tests replace it with a seeded random.Random.
rng = random.Random()

__all__ = ["AIError", "CONTEXT_PAIRS", "ChatResult", "answer_question", "pick_star"]


@dataclass
class ChatResult:
    # saved is False (id None) when the answer was made but the DB save failed.
    id: Optional[int]
    question: str
    answer: str
    created_at: datetime
    saved: bool


def pick_star(found: StarSearchResult, chooser=None) -> StarSearchResult:
    """Keep one random star from the search result.

    The group or the compared star is skipped when other stars exist, and stars whose
    chunks contain a content keyword are preferred over the rest.
    """
    if len(found.stars) <= 1:
        return found
    pool = [s for s in found.stars if not s.get("anchor")] or found.stars
    pool = [s for s in pool if s.get("matched")] or pool
    star = (chooser or rng).choice(pool)
    return StarSearchResult(stars=[star], missing_keywords=found.missing_keywords,
                            conditions=found.conditions)


def answer_question(db: Session, settings, user_id: int, message: str, *,
                    request_id: str, transport=None) -> ChatResult:
    """Answer one question and save it. Raises AIError when the AI call fails."""
    history = recent_chat_pairs(db, user_id, CONTEXT_PAIRS)
    previous = history[-1].question if history else None
    # Star data lookup never raises; with no data the AI answers without references.
    found = StarSearchResult()
    if settings.llm_configured():
        found = pick_star(search_stars(db.get_bind(), message, previous,
                                       request_id=request_id))
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
    # The model may copy the title or source line from the history; the server adds
    # the only ones.
    answer = remove_title_lines(remove_source_lines(answer)) or answer
    if found.stars:
        name = found.stars[0]["title"]
        answer = title_line(name) + "\n\n" + answer + "\n\n" + source_line(found)

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
