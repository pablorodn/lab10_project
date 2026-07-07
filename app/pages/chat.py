import asyncio

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from supabase import AsyncClient

from app.db.queries.messages import AgentMessage, get_session_messages
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
    current_session_id = session.id

    async def _messages() -> list[AgentMessage]:
        return await get_session_messages(db, current_session_id) if current_session_id else []

    async def _has_pending_confirmation() -> bool:
        if not current_session_id:
            return False
        return await has_pending_confirmation_for_session(db, current_session_id)

    # Ninguna de estas depende del resultado de las demas -- solo de current_session_id/
    # user_id, ya resueltos arriba -- asi que corren en un unico asyncio.gather en vez de
    # secuencial (cada round-trip a Supabase paga el RTT de red completo; 5 secuenciales
    # vs. 1 tanda paralela es la diferencia entre pagar ese costo 5 veces o 1). gather()
    # sin return_exceptions=True propaga la primera excepcion que ocurra, igual que un
    # await secuencial lo hacia antes -- no se cambia el manejo de errores. touch_session
    # no devuelve nada util pero va DENTRO del gather (no como task suelta aparte) para
    # que, si falla, la excepcion se propague en vez de perderse en el fondo.
    _, sessions, messages, profile, has_pending_confirmation = await asyncio.gather(
        touch_session(db, current_session_id),
        list_sessions(db, user_id=user_id, channel="web"),
        _messages(),
        get_profile(db, user_id),
        _has_pending_confirmation(),
    )
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
        messages: list[AgentMessage] = []
        new_current_session_id = None
        has_pending_confirmation = False
        active_session = None
        profile = await get_profile(db, user_id)
    else:

        async def _previous_session():
            if current_session_id and current_session_id != session_id:
                return await get_session_by_id(db, current_session_id)
            return None

        # Ninguna de estas depende del resultado de las demas -- solo del ownership ya
        # confirmado arriba -- asi que corren en un unico asyncio.gather en vez de
        # secuencial (mismo razonamiento que en chat_page: cada llamada paga el RTT de
        # red completo). gather() sin return_exceptions=True propaga la primera
        # excepcion igual que un await secuencial. touch_session va DENTRO del gather
        # (no como task suelta) para que un fallo no se pierda en el fondo.
        _, messages, has_pending_confirmation, profile, previous_session = await asyncio.gather(
            touch_session(db, session_id),
            get_session_messages(db, session_id),
            has_pending_confirmation_for_session(db, session_id),
            get_profile(db, user_id),
            _previous_session(),
        )
        new_current_session_id = session_id
        active_session = session
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
