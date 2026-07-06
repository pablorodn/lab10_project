import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.agent.graph import warmup_agent_runtime
from app.config import get_settings
from app.logging_config import configure_logging
from app.middleware.auth import AuthMiddleware
from app.pages import chat as chat_pages
from app.pages import index as index_pages
from app.pages import onboarding as onboarding_pages
from app.pages import settings as settings_pages
from app.routers import auth, chat, sessions
from app.template_filters import register_template_filters

templates = Jinja2Templates(directory="app/templates")
register_template_filters(templates)
configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    try:
        await warmup_agent_runtime()
        logger.info("Agent runtime warmed up.", extra={"event": "runtime_warmup"})
    except Exception as exc:  # pragma: no cover - infra dependent
        logger.warning(
            "Agent runtime warmup failed.",
            extra={"event": "runtime_warmup_failed", "reason": str(exc)},
        )
    yield


app = FastAPI(title="Lab10 Project", lifespan=lifespan)
settings = get_settings()
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, https_only=settings.is_production)
app.add_middleware(AuthMiddleware)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(index_pages.router)
app.include_router(auth.router)
app.include_router(onboarding_pages.router)
app.include_router(chat_pages.router)
app.include_router(settings_pages.router)
app.include_router(chat.router)
app.include_router(sessions.router)


@app.middleware("http")
async def request_logging_middleware(request, call_next):
    if not getattr(request.state, "request_id", None):
        request.state.request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    start = time.perf_counter()
    response = await call_next(request)
    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    logger.info(
        "HTTP request completed.",
        extra={
            "event": "http_request",
            "request_id": getattr(request.state, "request_id", None),
            "route": request.url.path,
            "status": response.status_code,
            "latency_ms": latency_ms,
        },
    )
    return response
