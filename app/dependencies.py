from typing import Any

from fastapi import Depends, HTTPException, Request
from supabase import AsyncClient

from app.db.client import create_server_client


async def get_db() -> AsyncClient:
    return await create_server_client()


async def validate_access_token(db: AsyncClient, access_token: str) -> dict[str, Any] | None:
    user_response = await db.auth.get_user(access_token)
    if not user_response or not user_response.user:
        return None
    return user_response.user.model_dump()


async def refresh_user_session(
    db: AsyncClient, refresh_token: str
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    refreshed = await db.auth.refresh_session(refresh_token)
    session = getattr(refreshed, "session", None)
    user = getattr(refreshed, "user", None)
    if not session or not user:
        return None, None, None
    return user.model_dump(), session.access_token, session.refresh_token


async def get_current_user(request: Request, db: AsyncClient = Depends(get_db)) -> dict[str, Any]:
    state_user_id = getattr(request.state, "user_id", None)
    if state_user_id:
        return {"id": str(state_user_id)}
    access_token = request.cookies.get("sb-access-token")
    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = await validate_access_token(db, access_token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid session")
    return user


async def get_current_user_id(
    request: Request, db: AsyncClient = Depends(get_db)
) -> str:
    user = await get_current_user(request, db)
    user_id = user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid session user")
    return str(user_id)
