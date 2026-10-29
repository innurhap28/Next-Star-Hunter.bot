"""Shared authentication and request-scoped database sessions."""
import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .crud.sessions import get_user_session, session_matches
from .crud.users import get_user
from .database import build_engine, build_session_factory
from .models import User

logger = logging.getLogger("next_star_hunter")
SESSION_REPLACED = {"error": "SESSION_REPLACED",
                    "message": "다른 곳에서 로그인되어 로그아웃되었습니다."}


def require_auth_configuration(request: Request):
    if not request.app.state.settings.auth_configured():
        raise HTTPException(
            503, {"error": "AUTH_NOT_CONFIGURED", "message": "서버 인증 설정을 확인해주세요."}
        )

def get_session_factory(request: Request):
    """Build the engine on first use. Raises 503 when DATABASE_URL is not usable."""
    if request.app.state.session_factory is None:
        try:
            url = request.app.state.settings.DATABASE_URL.get_secret_value()
            request.app.state.engine = build_engine(url)
            request.app.state.session_factory = build_session_factory(request.app.state.engine)
        except ValueError:
            raise HTTPException(
                503, {"error": "DB_NOT_CONFIGURED", "message": "서버 DB 설정을 확인해주세요."}
            ) from None
    return request.app.state.session_factory

def get_db(request: Request, _=Depends(require_auth_configuration)):
    with get_session_factory(request)() as session:
        try:
            yield session
        finally:
            session.rollback()

def check_login(request: Request, db: Session) -> tuple[Optional[User], str]:
    """Read the signed cookie and compare it with the stored session.

    Returns (user, state) where state is "ok", "logged_out", "stale" (user or
    session row gone) or "replaced" (the account logged in somewhere else).
    The cookie session is cleared for every state except "ok" and "logged_out".
    """
    user_id = request.session.get("user_id")
    if type(user_id) is not int:
        return None, "logged_out"
    user = get_user(db, user_id)
    row = get_user_session(db, user_id) if user is not None else None
    if user is not None and session_matches(row, request.session.get("sid")):
        return user, "ok"
    request.session.clear()
    if row is not None:
        logger.info("session_replaced user_id=%s request_id=%s",
                    user_id, request.state.request_id)
        return None, "replaced"
    return None, "stale"

def get_current_user(request: Request, db=Depends(get_db)) -> User:
    user, state = check_login(request, db)
    if state == "logged_out":
        raise HTTPException(401, {"error": "LOGIN_REQUIRED", "message": "로그인이 필요합니다."})
    if state == "replaced":
        raise HTTPException(401, SESSION_REPLACED)
    if state == "stale":
        raise HTTPException(401, {"error": "LOGIN_REQUIRED", "message": "다시 로그인해주세요."})
    return user
