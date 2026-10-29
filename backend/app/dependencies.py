"""Shared authentication and request-scoped database sessions."""
from fastapi import Depends, HTTPException, Request
from .database import build_engine, build_session_factory
from .models import User

def require_auth_configuration(request: Request):
    if not request.app.state.settings.auth_configured():
        raise HTTPException(503, {"error": "AUTH_NOT_CONFIGURED", "message": "서버 인증 설정을 확인해주세요."})

def get_db(request: Request, _=Depends(require_auth_configuration)):
    if request.app.state.session_factory is None:
        try:
            request.app.state.engine = build_engine(request.app.state.settings.DATABASE_URL.get_secret_value())
            request.app.state.session_factory = build_session_factory(request.app.state.engine)
        except ValueError:
            raise HTTPException(503, {"error": "DB_NOT_CONFIGURED", "message": "서버 DB 설정을 확인해주세요."}) from None
    with request.app.state.session_factory() as session:
        try:
            yield session
        finally:
            session.rollback()

def get_current_user(request: Request, db=Depends(get_db)) -> User:
    user_id = request.session.get("user_id")
    if type(user_id) is not int:
        raise HTTPException(401, {"error": "LOGIN_REQUIRED", "message": "로그인이 필요합니다."})
    user = db.get(User, user_id)
    if user is None:
        request.session.clear()
        raise HTTPException(401, {"error": "LOGIN_REQUIRED", "message": "다시 로그인해주세요."})
    return user
