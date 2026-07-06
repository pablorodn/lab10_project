from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from supabase import AsyncClient

from app.db.queries.messages import get_session_messages
from app.db.queries.profiles import get_profile
from app.db.queries.sessions import (
    get_or_create_active_session,
    get_session_by_id,
    list_sessions,
    touch_session,
)
from app.db.queries.tool_calls import has_pending_confirmation_for_session
from app.dependencies import get_current_user_id, get_db
from app.template_filters import register_template_filters

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
register_template_filters(templates)


@router.get("/chat", response_class=HTMLResponse)
async def chat_page(
    request: Request,
    db: AsyncClient = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    session = await get_or_create_active_session(db, user_id=user_id, channel="web")
    await touch_session(db, session.id)
    sessions = await list_sessions(db, user_id=user_id, channel="web")
    current_session_id = session.id
    messages = await get_session_messages(db, current_session_id) if current_session_id else []
    profile = await get_profile(db, user_id)
    has_pending_confirmation = False
    if current_session_id:
        has_pending_confirmation = await has_pending_confirmation_for_session(db, current_session_id)
    return templates.TemplateResponse(
        request,
        "chat.html",
        {
            "request": request,
            "agent_name": profile.agent_name if profile and profile.agent_name else "Agente",
            "active_nav": "chat",
            "sessions": sessions,
            "current_session_id": current_session_id,
            "messages": messages,
            "has_pending_confirmation": has_pending_confirmation,
            "sidebar_open": True,
        },
    )


@router.get("/chat/session/{session_id}", response_class=HTMLResponse)
async def chat_session(
    session_id: str,
    request: Request,
    db: AsyncClient = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
    current_session_id: str = Query(default=""),
):
    session = await get_session_by_id(db, session_id)
    previous_session = None
    if not session or session.user_id != user_id:
        messages = []
        new_current_session_id = None
        has_pending_confirmation = False
        active_session = None
    else:
        await touch_session(db, session_id)
        messages = await get_session_messages(db, session_id)
        new_current_session_id = session_id
        has_pending_confirmation = await has_pending_confirmation_for_session(db, session_id)
        active_session = session
        if current_session_id and current_session_id != session_id:
            previous_session = await get_session_by_id(db, current_session_id)
    profile = await get_profile(db, user_id)
    return templates.TemplateResponse(
        request,
        "partials/chat_session_switch.html",
        {
            "request": request,
            "messages": messages,
            "agent_name": profile.agent_name if profile and profile.agent_name else "Agente",
            "current_session_id": new_current_session_id,
            "has_pending_confirmation": has_pending_confirmation,
            "previous_session": previous_session,
            "active_session": active_session,
            "active_session_oob": True,
        },
    )
