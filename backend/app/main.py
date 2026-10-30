"""FastAPI entry point with account/chat APIs and a DB-independent health route."""
import logging
import secrets
from contextlib import asynccontextmanager
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException
from starlette.middleware.sessions import SessionMiddleware

from .config import Settings
from .logging_config import LOGGER_NAME, setup_console_logging, setup_file_logging
from .routers import admin, auth, chat, conversations, logs, pages

setup_console_logging()
logger = logging.getLogger(LOGGER_NAME)

LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
DEFAULT_PORTS = {"http": 80, "https": 443}


def is_same_origin(origin, request):
    """Origin must match Host; loopback names on the same scheme and port count as one."""
    host = request.headers.get("host", "")
    try:
        parsed = urlsplit(origin)
        if parsed.scheme not in DEFAULT_PORTS:
            return False
        if parsed.netloc == host:
            return True
        # Local docs opened at localhost may call 127.0.0.1 (or the reverse).
        target = urlsplit("//" + host)
        if parsed.hostname not in LOOPBACK_HOSTS or target.hostname not in LOOPBACK_HOSTS:
            return False
        scheme = parsed.scheme
        if scheme != request.url.scheme:
            return False
        return (parsed.port or DEFAULT_PORTS[scheme]) == (target.port or DEFAULT_PORTS[scheme])
    except ValueError:
        return False


def create_app(settings=None, session_factory=None, ai_transport=None):
    settings = settings or Settings()
    setup_file_logging(settings.LOG_FILE_PATH)
    @asynccontextmanager
    async def lifespan(app):
        yield
        if app.state.engine is not None:
            app.state.engine.dispose()

    app = FastAPI(title="Next Star Hunter API", version="0.1.0", lifespan=lifespan,
                  docs_url="/docs" if settings.ENABLE_API_DOCS else None,
                  redoc_url=None, openapi_url="/openapi.json" if settings.ENABLE_API_DOCS else None)
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.engine = None
    # Tests inject an httpx.MockTransport; None uses the real network.
    app.state.ai_transport = ai_transport
    # Without a configured stable key, account APIs return 503; health still works.
    secret_key = settings.SECRET_KEY.get_secret_value() or secrets.token_hex(32)
    app.add_middleware(SessionMiddleware, secret_key=secret_key,
                       session_cookie="next_star_session", max_age=8 * 60 * 60,
                       same_site="lax", https_only=settings.SESSION_HTTPS_ONLY)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        supplied = request.headers.get("x-request-id", "")
        try:
            request_id = str(UUID(supplied))
        except ValueError:
            request_id = str(uuid4())
        request.state.request_id = request_id
        logger.info("request_received method=%s path=%s request_id=%s",
                    request.method, request.url.path, request_id)
        # Browser writes must come from the same origin. CLI clients without Origin are supported.
        origin = request.headers.get("origin")
        bad_origin = bool(origin) and not is_same_origin(origin, request)
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and bad_origin:
            response = JSONResponse({"error": "ORIGIN_NOT_ALLOWED",
                                     "message": "허용되지 않은 요청 출처입니다."}, 403)
        else:
            response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request, error):
        if isinstance(error.detail, dict):
            body = error.detail
        else:
            body = {"error": "HTTP_ERROR", "message": str(error.detail)}
        return JSONResponse(body, error.status_code, headers=error.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        # Never echo input values: a validation error may contain a password.
        return JSONResponse({"error": "VALIDATION_ERROR", "message": "입력 형식을 확인해주세요.",
                             "fields": [list(item["loc"]) for item in error.errors()]}, 422)

    @app.exception_handler(SQLAlchemyError)
    async def db_error(request, error):
        logger.error("db_operation_failure request_id=%s error_type=%s",
                     request.state.request_id, type(error).__name__)
        message = "현재 DB 요청을 처리할 수 없습니다. 잠시 후 다시 시도해주세요."
        return JSONResponse({"error": "DB_UNAVAILABLE", "message": message}, 503)

    @app.get("/health", tags=["system"])
    async def health_check():
        return {"status": "ok", "service": "next-star-hunter"}

    app.mount("/static", StaticFiles(directory=str(pages.STATIC_DIR)), name="static")
    app.include_router(auth.router)
    app.include_router(chat.router)
    app.include_router(logs.router)
    app.include_router(conversations.router)
    app.include_router(admin.router)
    app.include_router(pages.router)
    return app

app = create_app()
