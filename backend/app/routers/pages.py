"""HTML pages for the web UI (chat, login/signup and admin)."""
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.exc import SQLAlchemyError

from ..dependencies import check_login, get_session_factory

# backend/app/routers/pages.py -> repository root
ROOT_DIR = Path(__file__).resolve().parents[3]
TEMPLATE_DIR = ROOT_DIR / "frontend" / "templates"
STATIC_DIR = ROOT_DIR / "frontend" / "static"

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
router = APIRouter(include_in_schema=False)

def page_login(request: Request) -> tuple[str, Optional[str]]:
    """(state, email) where state is "ok", "logged_out", "stale" or "replaced".

    See dependencies.check_login. If the DB cannot be reached the page falls
    back to the signed cookie alone (state "ok", email None); the page script
    then gets the real answer from the API.
    """
    if type(request.session.get("user_id")) is not int:
        return "logged_out", None
    if not request.app.state.settings.auth_configured():
        return "ok", None
    try:
        with get_session_factory(request)() as db:
            user, state = check_login(request, db)
            return state, user.email if user is not None else None
    except (HTTPException, SQLAlchemyError):
        return "ok", None

def login_state(request: Request) -> str:
    return page_login(request)[0]

def is_admin_email(request: Request, email: Optional[str]) -> bool:
    # getattr: ADMIN_EMAIL 설정이 없는 환경에서도 관리자 없음으로 동작하게 한다.
    admin_email = (getattr(request.app.state.settings, "ADMIN_EMAIL", "") or "").strip().lower()
    return bool(admin_email) and bool(email) and email.strip().lower() == admin_email

@router.get("/")
def chat_page(request: Request):
    state = login_state(request)
    if state == "replaced":
        return RedirectResponse("/auth?reason=session_replaced", status_code=303)
    if state != "ok":
        return RedirectResponse("/auth", status_code=303)
    context = {"page_title": "스타 헌팅 · Next Star Hunter"}
    return templates.TemplateResponse(request, "chat.html", context)

@router.get("/auth")
def auth_page(request: Request):
    # A replaced or stale session is cleared here, so the login form still opens.
    if login_state(request) == "ok":
        return RedirectResponse("/", status_code=303)
    context = {"page_title": "로그인 · Next Star Hunter"}
    return templates.TemplateResponse(request, "auth.html", context)

@router.get("/admin")
def admin_page(request: Request):
    state, email = page_login(request)
    if state == "replaced":
        return RedirectResponse("/auth?reason=session_replaced", status_code=303)
    if state != "ok":
        return RedirectResponse("/auth", status_code=303)
    if not is_admin_email(request, email):
        return RedirectResponse("/", status_code=303)
    context = {"page_title": "관리자 · Next Star Hunter"}
    return templates.TemplateResponse(request, "admin.html", context)
