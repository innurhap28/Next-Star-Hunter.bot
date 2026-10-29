"""Chat API: recent context, AI call, and chat log saving."""
import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from ..ai_client import AIError, ask_ai
from ..dependencies import get_current_user, get_db
from ..models import ChatLog, utc_now
from ..openapi_errors import CHAT_ERRORS
from ..schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/api", tags=["chat"])
logger = logging.getLogger("next_star_hunter")
CONTEXT_PAIRS = 5


def recent_history(db, user_id):
    """The user's latest Q/A pairs, oldest first."""
    rows = db.scalars(
        select(ChatLog).where(ChatLog.user_id == user_id)
        .order_by(ChatLog.created_at.desc(), ChatLog.id.desc()).limit(CONTEXT_PAIRS)
    ).all()
    return list(reversed(rows))


@router.post("/chat", response_model=ChatResponse, responses=CHAT_ERRORS)
def chat(body: ChatRequest, request: Request, user=Depends(get_current_user),
         db=Depends(get_db)):
    settings = request.app.state.settings
    request_id = request.state.request_id
    history = recent_history(db, user.id)
    # Message text and answers are never logged; only ids, timing, and error codes.
    logger.info("ai_call_start user_id=%s request_id=%s", user.id, request_id)
    started = time.monotonic()
    try:
        answer = ask_ai(settings, history, body.message, transport=request.app.state.ai_transport)
    except AIError as error:
        logger.warning("ai_call_failure request_id=%s error=%s reason=%s",
                       request_id, error.code, error.reason)
        raise HTTPException(error.status_code,
                            {"error": error.code, "message": error.message}) from None
    latency_ms = int((time.monotonic() - started) * 1000)
    logger.info("ai_call_success request_id=%s latency_ms=%s", request_id, latency_ms)

    log = ChatLog(user_id=user.id, question=body.message, answer=answer, created_at=utc_now())
    db.add(log)
    try:
        db.commit()
    except SQLAlchemyError as error:
        db.rollback()
        # The answer is already made, so return it and tell the client it was not saved.
        logger.error("db_save_failure user_id=%s request_id=%s error_type=%s",
                     user.id, request_id, type(error).__name__)
        return ChatResponse(id=None, question=body.message, answer=answer,
                            created_at=log.created_at, saved=False)
    logger.info("db_save_success user_id=%s chat_id=%s request_id=%s",
                user.id, log.id, request_id)
    return ChatResponse(id=log.id, question=log.question, answer=log.answer,
                        created_at=log.created_at, saved=True)
