"""HTML pages for the web UI (chat and login/signup)."""
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

# backend/app/routers/pages.py -> repository root
ROOT_DIR = Path(__file__).resolve().parents[3]
TEMPLATE_DIR = ROOT_DIR / "frontend" / "templates"
STATIC_DIR = ROOT_DIR / "frontend" / "static"

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
router = APIRouter(include_in_schema=False)

def is_logged_in(request: Request) -> bool:
    # Only reads the signed session cookie; stale ones are handled by /api/me in the script.
    return type(request.session.get("user_id")) is int

@router.get("/")
def chat_page(request: Request):
    if not is_logged_in(request):
        return RedirectResponse("/auth", status_code=303)
    context = {"page_title": "스타 헌팅 · Next Star Hunter"}
    return templates.TemplateResponse(request, "chat.html", context)

@router.get("/auth")
def auth_page(request: Request):
    if is_logged_in(request):
        return RedirectResponse("/", status_code=303)
    context = {"page_title": "로그인 · Next Star Hunter"}
    return templates.TemplateResponse(request, "auth.html", context)
