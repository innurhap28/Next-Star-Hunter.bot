"""Chat API: HTTP layer only. The chat flow lives in services/chat.py."""
from fastapi import APIRouter, Depends, HTTPException, Request

from ..dependencies import get_current_user, get_db
from ..openapi_errors import CHAT_ERRORS, CONVERSATION_NOT_FOUND
from ..schemas.chat import ChatRequest, ChatResponse
from ..services.chat import AIError, ConversationNotFound, answer_question

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse, responses=CHAT_ERRORS)
def chat(body: ChatRequest, request: Request, user=Depends(get_current_user),
         db=Depends(get_db)):
    try:
        result = answer_question(db, request.app.state.settings, user.id, body.message,
                                 request_id=request.state.request_id,
                                 transport=request.app.state.ai_transport,
                                 conversation_id=body.conversation_id)
    except ConversationNotFound:
        raise HTTPException(404, CONVERSATION_NOT_FOUND) from None
    except AIError as error:
        raise HTTPException(error.status_code,
                            {"error": error.code, "message": error.message}) from None
    return ChatResponse(id=result.id, question=result.question, answer=result.answer,
                        created_at=result.created_at, saved=result.saved,
                        conversation_id=result.conversation_id)
