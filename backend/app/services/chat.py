"""Chat flow: recent context, star search, AI call, source line, and log saving.

Context and follow-up stars come only from the same conversation. HTTP concerns
stay in routers/chat.py. AIError from the AI call and ConversationNotFound are
raised as is so the router can map them to an HTTP response.
"""
import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..crud.chat_logs import recent_chat_pairs, save_chat_log
from ..crud.conversations import conversation_answers, get_user_conversation
from ..models import utc_now
from .ai_client import RANDOM_PICK_NOTE, AIError, ask_ai
from .star_search import (
    ANOTHER_RE,
    ASK_PICK_RE,
    MALGO_NAME_RE,
    RANDOM_CONDITION,
    REFER_RE,
    StarSearchResult,
    answered_star,
    display_name,
    find_star,
    format_reference,
    is_random_request,
    is_star_name,
    parse_query,
    random_star,
    remove_source_lines,
    remove_title_lines,
    search_stars,
    source_line,
    strip_josa,
    title_line,
)

logger = logging.getLogger("next_star_hunter")
CONTEXT_PAIRS = 5
# Picks the one star to recommend. Tests replace it with a seeded random.Random.
rng = random.Random()

__all__ = ["AIError", "CONTEXT_PAIRS", "ChatResult", "ConversationNotFound",
           "answer_question", "follow_up_mode", "pick_star"]


class ConversationNotFound(Exception):
    """The conversation_id is missing or belongs to another user (same 404 for both)."""


@dataclass
class ChatResult:
    # saved is False (id None) when the answer was made but the DB save failed.
    id: Optional[int]
    question: str
    answer: str
    created_at: datetime
    saved: bool
    # None only when the DB save failed.
    conversation_id: Optional[int] = None


def pick_star(found: StarSearchResult, chooser=None, exclude=()) -> StarSearchResult:
    """Keep one random star from the search result.

    The group or the compared star is skipped when other stars exist, and stars whose
    chunks contain a content keyword are preferred over the rest. Stars in exclude
    (titles or display names already recommended) are never picked.
    """
    if exclude:
        skip = set(exclude)
        stars = [s for s in found.stars
                 if s["title"] not in skip and display_name(s["title"]) not in skip]
        found = StarSearchResult(stars=stars, missing_keywords=found.missing_keywords,
                                 conditions=found.conditions)
    if len(found.stars) <= 1:
        return found
    pool = [s for s in found.stars if not s.get("anchor")] or found.stars
    pool = [s for s in pool if s.get("matched")] or pool
    star = (chooser or rng).choice(pool)
    return StarSearchResult(stars=[star], missing_keywords=found.missing_keywords,
                            conditions=found.conditions)


def _names_a_star_before_malgo(message: str, previous_star: Optional[str],
                               is_star: Optional[Callable[[str], bool]]) -> bool:
    """'강혜원 말고': the word before '말고' is the previous star or another star."""
    own = {previous_star, display_name(previous_star)} if previous_star else set()
    for m in MALGO_NAME_RE.finditer(message):
        word = m.group(1)
        if own & {word, strip_josa(word)}:
            return True
        if is_star is not None and is_star(word):
            return True
    return False


def follow_up_mode(message: str, previous_star: Optional[str],
                   is_star: Optional[Callable[[str], bool]] = None) -> str:
    """How to pick the star for a question after an answer that recommended one.

    'another': asks for a different person, so search again without the stars already
    recommended. 'similar': asks for someone similar to the previous star ('그 사람이랑
    비슷한 가수'). 'same': refers back ('그 사람', '걔') to the previous star.
    'same_unless_named': no new conditions, so keep the previous star unless the question
    names another star. 'search': new conditions, or nothing was recommended before.
    'random': a random pick with no conditions ('오늘의 랜덤 스타를 추천해줘').
    is_star(word) tells whether a word is a star name ('강혜원 말고' vs '노래 말고').
    """
    if is_random_request(message):
        return "random"
    if ANOTHER_RE.search(message) or _names_a_star_before_malgo(message, previous_star,
                                                                is_star):
        return "another"
    if not previous_star:
        return "search"
    q = parse_query(message)
    if q.similar and REFER_RE.search(message):
        return "similar"
    if REFER_RE.search(message):
        return "same"
    if q.structured() or q.similar or (q.keywords and ASK_PICK_RE.search(message)):
        return "search"
    return "same_unless_named"


def _condition_question(history) -> Optional[str]:
    """The latest question with structured conditions (else the latest question)."""
    for log in reversed(history):
        if parse_query(log.question).structured():
            return log.question
    return history[-1].question if history else None


def _last_search_was_random(history) -> bool:
    """The latest question that asked for a new star was a random request.

    Questions about the star just recommended ('걔 키 몇이야?') and '다른 사람' requests
    are skipped; a question with conditions or a pick word ('추천', '누구') ends the walk.
    """
    for log in reversed(history):
        if is_random_request(log.question):
            return True
        if ANOTHER_RE.search(log.question) or REFER_RE.search(log.question):
            continue
        if parse_query(log.question).structured() or ASK_PICK_RE.search(log.question):
            return False
    return False


def _no_new_conditions(message: str) -> bool:
    """'다른 사람', '강혜원 말고': no condition besides the star to leave out."""
    q = parse_query(message)
    if q.structured() or q.similar:
        return False
    left_out = set()
    for m in MALGO_NAME_RE.finditer(message):
        left_out.update((m.group(1), strip_josa(m.group(1))))
    return all(k in left_out for k in q.keywords)


def _recommended(answers) -> tuple[str, ...]:
    titles = (answered_star(answer) for answer in answers)
    return tuple(dict.fromkeys(t for t in titles if t))


def _find_reference(engine, message: str, history, request_id: str,
                    answers=None) -> StarSearchResult:
    """answers: every answer of the conversation (defaults to the context history)."""
    if answers is None:
        answers = [log.answer for log in history]
    previous_star = answered_star(history[-1].answer) if history else None
    mode = follow_up_mode(message, previous_star,
                          lambda word: is_star_name(engine, word, request_id=request_id))
    if mode == "another" and _no_new_conditions(message) and _last_search_was_random(history):
        # '다른 사람' after a random pick: another random one
        mode = "random"
    if mode == "random":
        logger.info("star_pick request_id=%s mode=%s", request_id, mode)
        return random_star(engine, _recommended(answers), request_id=request_id)
    if mode == "similar":
        # '그 사람이랑 비슷한 가수': search with the previous star's name in place of '그 사람'
        named = REFER_RE.sub(display_name(previous_star), message, count=1)
        logger.info("star_pick request_id=%s mode=%s", request_id, mode)
        found = search_stars(engine, named, request_id=request_id)
        return pick_star(found)
    if mode in ("same", "same_unless_named"):
        found = find_star(engine, previous_star, message, request_id=request_id,
                          unless_other_named=mode == "same_unless_named")
        if found is not None:
            logger.info("star_pick request_id=%s mode=%s", request_id, mode)
            return found
        # the previous star is not in the data (or another star is named): search as usual
        mode = "search"
    exclude: tuple[str, ...] = ()
    if mode == "another":
        exclude = _recommended(answers)
    logger.info("star_pick request_id=%s mode=%s", request_id, mode)
    found = search_stars(engine, message, _condition_question(history),
                         request_id=request_id, exclude=exclude)
    return pick_star(found, exclude=exclude)


def answer_question(db: Session, settings, user_id: int, message: str, *,
                    request_id: str, transport=None,
                    conversation_id: Optional[int] = None) -> ChatResult:
    """Answer one question and save it in the conversation (a new one when None).

    Raises ConversationNotFound before the AI call when the id is not the user's,
    and AIError when the AI call fails.
    """
    conversation = None
    if conversation_id is not None:
        conversation = get_user_conversation(db, user_id, conversation_id)
        if conversation is None:
            raise ConversationNotFound()
    history = recent_chat_pairs(db, user_id, conversation_id, CONTEXT_PAIRS)
    # Star data lookup never raises; with no data the AI answers without references.
    found = StarSearchResult()
    if settings.llm_configured():
        found = _find_reference(db.get_bind(), message, history, request_id,
                                conversation_answers(db, conversation_id))
    # Message text and answers are never logged; only ids, timing, and error codes.
    logger.info("ai_call_start user_id=%s request_id=%s", user_id, request_id)
    started = time.monotonic()
    try:
        references = format_reference(found)
        if references and RANDOM_CONDITION in found.conditions:
            references = RANDOM_PICK_NOTE + "\n\n" + references
        answer = ask_ai(settings, history, message, transport=transport,
                        references=references)
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
        log = save_chat_log(db, user_id, message, answer, created_at,
                            conversation=conversation)
    except SQLAlchemyError as error:
        # The answer is already made, so return it and tell the client it was not saved.
        logger.error("db_save_failure user_id=%s request_id=%s error_type=%s",
                     user_id, request_id, type(error).__name__)
        return ChatResult(id=None, question=message, answer=answer,
                          created_at=created_at, saved=False)
    logger.info("db_save_success user_id=%s chat_id=%s conversation_id=%s request_id=%s",
                user_id, log.id, log.conversation_id, request_id)
    return ChatResult(id=log.id, question=log.question, answer=log.answer,
                      created_at=log.created_at, saved=True,
                      conversation_id=log.conversation_id)
