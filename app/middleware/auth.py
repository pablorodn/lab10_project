import logging
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import RedirectResponse, Response

from app.config import get_settings
from app.db.client import create_server_client
from app.dependencies import refresh_user_session, validate_access_token

PUBLIC_PATHS: tuple[str, ...] = ("/login", "/signup", "/static", "/robots.txt", "/favicon.ico")
SERVER_TO_SERVER_PATHS: tuple[str, ...] = ()
logger = logging.getLogger(__name__)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = request_id
        path = request.url.path
        is_public = any(path.startswith(prefix) for prefix in PUBLIC_PATHS)
        is_s2s = any(path.startswith(prefix) for prefix in SERVER_TO_SERVER_PATHS)
        if not is_public and not is_s2s:
            access_token = request.cookies.get("sb-access-token")
            refresh_token = request.cookies.get("sb-refresh-token")
            if not access_token:
                logger.info(
                    "Redirecting unauthenticated request to login.",
                    extra={"event": "auth_redirect", "request_id": request_id, "path": path, "reason": "missing_access_token"},
                )
                return RedirectResponse(url="/login", status_code=307)
            try:
                db = await create_server_client()
                user = None
                rotated_access_token: str | None = None
                rotated_refresh_token: str | None = None
                try:
                    user = await validate_access_token(db, access_token)
                except Exception as exc:
                    logger.info(
                        "Access token validation failed; trying refresh flow.",
                        extra={
                            "event": "auth_access_token_invalid",
                            "request_id": request_id,
                            "path": path,
                            "reason": str(exc),
                        },
                    )
                if not user and refresh_token:
                    user, rotated_access_token, rotated_refresh_token = await refresh_user_session(
                        db, refresh_token
                    )
                    if user:
                        logger.info(
                            "Session token rotated successfully.",
                            extra={
                                "event": "auth_session_refreshed",
                                "request_id": request_id,
                                "path": path,
                            },
                        )
                if not user:
                    logger.info(
                        "Redirecting request due to invalid session.",
                        extra={"event": "auth_redirect", "request_id": request_id, "path": path, "reason": "invalid_or_expired_token"},
                    )
                    return RedirectResponse(url="/login", status_code=307)
                request.state.user_id = str(user.get("id") or "")
            except Exception as exc:
                logger.warning(
                    "Redirecting request due to auth provider error.",
                    extra={
                        "event": "auth_redirect",
                        "request_id": request_id,
                        "path": path,
                        "reason": str(exc),
                    },
                )
                return RedirectResponse(url="/login", status_code=307)
            response: Response = await call_next(request)
            if rotated_access_token and rotated_refresh_token:
                secure_cookies = get_settings().is_production
                response.set_cookie(
                    "sb-access-token",
                    rotated_access_token,
                    httponly=True,
                    secure=secure_cookies,
                )
                response.set_cookie(
                    "sb-refresh-token",
                    rotated_refresh_token,
                    httponly=True,
                    secure=secure_cookies,
                )
            return response
        return await call_next(request)
