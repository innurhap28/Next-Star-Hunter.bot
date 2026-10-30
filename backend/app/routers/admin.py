"""Admin-only read APIs: service totals, users and recent chats."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request

from ..crud.chat_logs import count_chats, count_chats_today, list_chats_with_email
from ..crud.users import count_users, list_users_with_chat_stats
from ..dependencies import get_db, require_admin
from ..openapi_errors import admin_errors
from ..schemas.admin import AdminChatList, AdminStats, AdminUserList

router = APIRouter(prefix="/api/admin", tags=["admin"])
logger = logging.getLogger("next_star_hunter")


def log_admin_view(request: Request, user) -> None:
    # Only who looked at which path; no query values or returned data.
    logger.info("admin_view user_id=%s path=%s request_id=%s",
                user.id, request.url.path, request.state.request_id)


@router.get("/stats", response_model=AdminStats, responses=admin_errors())
def stats(request: Request, user=Depends(require_admin), db=Depends(get_db)):
    log_admin_view(request, user)
    return AdminStats(users=count_users(db), chats=count_chats(db),
                      chats_today=count_chats_today(db))


@router.get("/users", response_model=AdminUserList, responses=admin_errors("limit", "offset"))
def users(request: Request, limit: int = Query(50, ge=1, le=100),
          offset: int = Query(0, ge=0), user=Depends(require_admin), db=Depends(get_db)):
    log_admin_view(request, user)
    return AdminUserList(items=list_users_with_chat_stats(db, limit, offset),
                         total=count_users(db))


@router.get("/chats", response_model=AdminChatList, responses=admin_errors("user_id", "limit"))
def chats(request: Request, user_id: Optional[int] = Query(None),
          limit: int = Query(50, ge=1, le=100), user=Depends(require_admin),
          db=Depends(get_db)):
    log_admin_view(request, user)
    return AdminChatList(items=list_chats_with_email(db, user_id, limit))
