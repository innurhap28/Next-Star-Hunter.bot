"""Account APIs for the Next Star Hunter web client."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..dependencies import get_current_user, get_db
from ..models import User
from ..openapi_errors import LOGIN_ERRORS, LOGOUT_ERRORS, ME_ERRORS, REGISTER_ERRORS
from ..schemas import Credentials, UserPublic
from ..security import hash_password, verify_password

router = APIRouter(prefix="/api", tags=["accounts"])
logger = logging.getLogger("next_star_hunter")
# Unknown-account logins also run the same password verification operation.
DUMMY_HASH = hash_password("not-a-login-password")

@router.post("/auth/register", response_model=UserPublic, status_code=201,
             responses=REGISTER_ERRORS)
def register(body: Credentials, request: Request, db=Depends(get_db)):
    if db.scalar(select(User).where(User.email == str(body.email))) is not None:
        raise HTTPException(409, {"error": "EMAIL_EXISTS", "message": "이미 가입된 이메일입니다."})
    user = User(email=str(body.email), password_hash=hash_password(body.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        # Re-check after the rollback to handle a concurrent registration race.
        if db.scalar(select(User).where(User.email == str(body.email))) is not None:
            raise HTTPException(
                409, {"error": "EMAIL_EXISTS", "message": "이미 가입된 이메일입니다."}
            ) from None
        raise error
    logger.info("db_save_success action=register user_id=%s request_id=%s",
                user.id, request.state.request_id)
    return user

@router.post("/auth/login", response_model=UserPublic, responses=LOGIN_ERRORS)
def login(body: Credentials, request: Request, db=Depends(get_db)):
    user = db.scalar(select(User).where(User.email == str(body.email)))
    password_hash = user.password_hash if user else DUMMY_HASH
    if not verify_password(body.password, password_hash) or user is None:
        raise HTTPException(401, {"error": "INVALID_CREDENTIALS",
                                  "message": "이메일 또는 비밀번호를 확인해주세요."})
    request.session.clear()
    request.session["user_id"] = user.id
    logger.info("login_success user_id=%s request_id=%s", user.id, request.state.request_id)
    return user

@router.post("/auth/logout", status_code=204, responses=LOGOUT_ERRORS)
def logout(request: Request, user=Depends(get_current_user)):
    request.session.clear()
    return Response(status_code=204)

@router.get("/me", response_model=UserPublic, responses=ME_ERRORS)
def me(user=Depends(get_current_user)):
    return user
