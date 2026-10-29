"""HTML pages for the web UI (chat and login/signup)."""
from pathlib import Path

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

def login_state(request: Request) -> str:
    """"ok", "logged_out", "stale" or "replaced" (see dependencies.check_login).

    If the DB cannot be reached the page falls back to the signed cookie alone;
    the page script then gets the real answer from GET /api/me.
    """
    if type(request.session.get("user_id")) is not int:
        return "logged_out"
    if not request.app.state.settings.auth_configured():
        return "ok"
    try:
        with get_session_factory(request)() as db:
            return check_login(request, db)[1]
    except (HTTPException, SQLAlchemyError):
        return "ok"

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
