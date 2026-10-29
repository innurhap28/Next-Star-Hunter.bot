"""Chat history API: the logged-in user's saved questions and answers."""
from fastapi import APIRouter, Depends, Query

from ..crud.chat_logs import list_user_chats
from ..dependencies import get_current_user, get_db
from ..openapi_errors import HISTORY_ERRORS
from ..schemas.logs import ChatHistoryResponse

router = APIRouter(prefix="/api", tags=["chat"])


@router.get("/me/chats", response_model=ChatHistoryResponse, responses=HISTORY_ERRORS)
def my_chats(limit: int = Query(20, ge=1, le=100), user=Depends(get_current_user),
             db=Depends(get_db)):
    # Only the logged-in user's rows; the same query feeds the chat context.
    return ChatHistoryResponse(items=list_user_chats(db, user.id, limit))
