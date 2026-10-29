"""FastAPI entry point with account APIs and a DB-independent health route."""
import logging
import secrets
from contextlib import asynccontextmanager
from uuid import UUID, uuid4
from urllib.parse import urlsplit
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.exc import SQLAlchemyError
from .config import Settings
from .routers import auth

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("next_star_hunter")

def create_app(settings=None, session_factory=None):
    settings = settings or Settings()
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
    # Without a configured stable key, account APIs return 503; health still works.
    app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY.get_secret_value() or secrets.token_hex(32),
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
        logger.info("request_received method=%s path=%s request_id=%s", request.method, request.url.path, request_id)
        # Browser writes must come from the same origin. CLI clients without Origin are supported.
        origin = request.headers.get("origin")
        try:
            parsed = urlsplit(origin) if origin else None
            bad_origin = parsed is not None and (parsed.scheme not in {"http", "https"} or parsed.netloc != request.headers.get("host"))
        except ValueError:
            bad_origin = True
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and bad_origin:
        #if request.method in {"PUT", "PATCH", "DELETE"} and bad_origin:
            response = JSONResponse({"error": "ORIGIN_NOT_ALLOWED", "message": "허용되지 않은 요청 출처입니다."}, 403)
        else:
            response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request, error):
        body = error.detail if isinstance(error.detail, dict) else {"error": "HTTP_ERROR", "message": str(error.detail)}
        return JSONResponse(body, error.status_code, headers=error.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        # Never echo input values: a validation error may contain a password.
        return JSONResponse({"error": "VALIDATION_ERROR", "message": "입력 형식을 확인해주세요.",
                             "fields": [list(item["loc"]) for item in error.errors()]}, 422)

    @app.exception_handler(SQLAlchemyError)
    async def db_error(request, error):
        logger.error("db_operation_failure request_id=%s error_type=%s", request.state.request_id, type(error).__name__)
        return JSONResponse({"error": "DB_UNAVAILABLE", "message": "현재 DB 요청을 처리할 수 없습니다. 잠시 후 다시 시도해주세요."}, 503)

    @app.get("/health", tags=["system"])
    async def health_check():
        return {"status": "ok", "service": "next-star-hunter"}

    app.include_router(auth.router)
    return app

app = create_app()
