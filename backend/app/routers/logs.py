"""Chat history API: the logged-in user's saved questions and answers."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from ..crud.chat_logs import delete_user_chat, list_user_chats
from ..dependencies import get_current_user, get_db
from ..openapi_errors import DELETE_CHAT_ERRORS, HISTORY_ERRORS
from ..schemas.logs import ChatHistoryResponse

router = APIRouter(prefix="/api", tags=["chat"])
logger = logging.getLogger("next_star_hunter")


@router.get("/me/chats", response_model=ChatHistoryResponse, responses=HISTORY_ERRORS)
def my_chats(limit: int = Query(20, ge=1, le=100), user=Depends(get_current_user),
             db=Depends(get_db)):
    # Only the logged-in user's rows; the same query feeds the chat context.
    return ChatHistoryResponse(items=list_user_chats(db, user.id, limit))


@router.delete("/me/chats/{chat_id}", status_code=204, responses=DELETE_CHAT_ERRORS)
def delete_my_chat(chat_id: int, request: Request, user=Depends(get_current_user),
                   db=Depends(get_db)):
    # A missing row and another user's row get the same 404.
    if not delete_user_chat(db, user.id, chat_id):
        raise HTTPException(404, {"error": "CHAT_NOT_FOUND", "message": "대화를 찾을 수 없습니다."})
    logger.info("chat_deleted user_id=%s chat_id=%s request_id=%s",
                user.id, chat_id, request.state.request_id)
    return Response(status_code=204)
