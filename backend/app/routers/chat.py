"""Chat API: HTTP layer only. The chat flow lives in services/chat.py."""
from fastapi import APIRouter, Depends, HTTPException, Request

from ..dependencies import get_current_user, get_db
from ..openapi_errors import CHAT_ERRORS
from ..schemas import ChatRequest, ChatResponse
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
