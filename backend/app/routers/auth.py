"""Account APIs for the Next Star Hunter web client."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.exc import IntegrityError

from ..crud.sessions import delete_user_session, new_session_id, replace_user_session
from ..crud.users import create_user, get_user_by_email
from ..dependencies import get_current_user, get_db, is_admin
from ..openapi_errors import LOGIN_ERRORS, LOGOUT_ERRORS, ME_ERRORS, REGISTER_ERRORS
from ..schemas.auth import Credentials, MePublic, UserPublic
from ..security import hash_password, verify_password

router = APIRouter(prefix="/api", tags=["accounts"])
logger = logging.getLogger("next_star_hunter")
# Unknown-account logins also run the same password verification operation.
DUMMY_HASH = hash_password("not-a-login-password")

@router.post("/auth/register", response_model=UserPublic, status_code=201,
             responses=REGISTER_ERRORS)
def register(body: Credentials, request: Request, db=Depends(get_db)):
    email = str(body.email)
    if get_user_by_email(db, email) is not None:
        raise HTTPException(409, {"error": "EMAIL_EXISTS", "message": "이미 가입된 이메일입니다."})
    try:
        user = create_user(db, email, hash_password(body.password))
    except IntegrityError as error:
        # Re-check after the rollback to handle a concurrent registration race.
        if get_user_by_email(db, email) is not None:
            raise HTTPException(
                409, {"error": "EMAIL_EXISTS", "message": "이미 가입된 이메일입니다."}
            ) from None
        raise error
    logger.info("db_save_success action=register user_id=%s request_id=%s",
                user.id, request.state.request_id)
    return user

@router.post("/auth/login", response_model=UserPublic, responses=LOGIN_ERRORS)
def login(body: Credentials, request: Request, db=Depends(get_db)):
    user = get_user_by_email(db, str(body.email))
    password_hash = user.password_hash if user else DUMMY_HASH
    if not verify_password(body.password, password_hash) or user is None:
        raise HTTPException(401, {"error": "INVALID_CREDENTIALS",
                                  "message": "이메일 또는 비밀번호를 확인해주세요."})
    # One active session per account: this login replaces any earlier one.
    session_id = new_session_id()
    replace_user_session(db, user.id, session_id)
    request.session.clear()
    request.session["user_id"] = user.id
    request.session["sid"] = session_id
    logger.info("login_success user_id=%s request_id=%s", user.id, request.state.request_id)
    return user

@router.post("/auth/logout", status_code=204, responses=LOGOUT_ERRORS)
def logout(request: Request, user=Depends(get_current_user), db=Depends(get_db)):
    # Only removes the row if it is still this browser's session.
    delete_user_session(db, user.id, request.session.get("sid"))
    request.session.clear()
    return Response(status_code=204)

@router.get("/me", response_model=MePublic, responses=ME_ERRORS)
def me(request: Request, user=Depends(get_current_user)):
    return MePublic(id=user.id, email=user.email, created_at=user.created_at,
                    is_admin=is_admin(request.app.state.settings, user))
