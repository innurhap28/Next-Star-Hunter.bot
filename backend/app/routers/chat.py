"""Chat API: HTTP layer only. The chat flow lives in services/chat.py."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..crud.chat_logs import list_user_chats
from ..dependencies import get_current_user, get_db
from ..openapi_errors import CHAT_ERRORS, HISTORY_ERRORS
from ..schemas import ChatHistoryResponse, ChatRequest, ChatResponse
from ..services.chat import AIError, answer_question

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse, responses=CHAT_ERRORS)
def chat(body: ChatRequest, request: Request, user=Depends(get_current_user),
         db=Depends(get_db)):
    try:
        result = answer_question(db, request.app.state.settings, user.id, body.message,
                                 request_id=request.state.request_id,
                                 transport=request.app.state.ai_transport)
    except AIError as error:
        raise HTTPException(error.status_code,
                            {"error": error.code, "message": error.message}) from None
    return ChatResponse(id=result.id, question=result.question, answer=result.answer,
                        created_at=result.created_at, saved=result.saved)


@router.get("/me/chats", response_model=ChatHistoryResponse, responses=HISTORY_ERRORS)
def my_chats(limit: int = Query(20, ge=1, le=100), user=Depends(get_current_user),
             db=Depends(get_db)):
    # Only the logged-in user's rows; the same query feeds the chat context.
    return ChatHistoryResponse(items=list_user_chats(db, user.id, limit))
