"""Conversation (chat room) API: the logged-in user's rooms and their chats."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from ..crud.conversations import (
    delete_user_conversation,
    get_user_conversation,
    list_conversation_chats,
    list_user_conversations,
)
from ..dependencies import get_current_user, get_db
from ..openapi_errors import (
    CONVERSATION_CHATS_ERRORS,
    CONVERSATION_LIST_ERRORS,
    CONVERSATION_NOT_FOUND,
    DELETE_CONVERSATION_ERRORS,
)
from ..schemas.conversations import ConversationChats, ConversationList

router = APIRouter(prefix="/api/me/conversations", tags=["chat"])
logger = logging.getLogger("next_star_hunter")


@router.get("", response_model=ConversationList, responses=CONVERSATION_LIST_ERRORS)
def my_conversations(limit: int = Query(50, ge=1, le=100), user=Depends(get_current_user),
                     db=Depends(get_db)):
    return ConversationList(items=list_user_conversations(db, user.id, limit))


@router.get("/{conversation_id}/chats", response_model=ConversationChats,
            responses=CONVERSATION_CHATS_ERRORS)
def conversation_chats(conversation_id: int, user=Depends(get_current_user),
                       db=Depends(get_db)):
    # A missing room and another user's room get the same 404.
    conversation = get_user_conversation(db, user.id, conversation_id)
    if conversation is None:
        raise HTTPException(404, CONVERSATION_NOT_FOUND)
    return ConversationChats(conversation=conversation,
                             items=list_conversation_chats(db, conversation.id))


@router.delete("/{conversation_id}", status_code=204, responses=DELETE_CONVERSATION_ERRORS)
def delete_conversation(conversation_id: int, request: Request,
                        user=Depends(get_current_user), db=Depends(get_db)):
    if not delete_user_conversation(db, user.id, conversation_id):
        raise HTTPException(404, CONVERSATION_NOT_FOUND)
    logger.info("conversation_deleted user_id=%s conversation_id=%s request_id=%s",
                user.id, conversation_id, request.state.request_id)
    return Response(status_code=204)
