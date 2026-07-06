from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from supabase import AsyncClient

from app.agent.model import CURATED_CHAT_MODELS, validate_model_selection
from app.db.queries.profiles import get_profile, upsert_profile
from app.db.queries.tools import list_enabled_tool_ids, replace_enabled_tools
from app.dependencies import get_current_user_id, get_db
from app.tools.catalog import TOOL_CATALOG

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    db: AsyncClient = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    profile = await get_profile(db, user_id)
    enabled_tool_ids = await list_enabled_tool_ids(db, user_id)
    profile_payload = {
        "name": profile.name if profile and profile.name else "",
        "agent_name": profile.agent_name if profile and profile.agent_name else "Agente",
        "agent_system_prompt": (
            profile.agent_system_prompt
            if profile and profile.agent_system_prompt
            else ""
        ),
    }
    stored_default_model = getattr(profile, "default_model", None) if profile else None
    selected_model = validate_model_selection(stored_default_model, user_id=user_id)
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "request": request,
            "active_nav": "settings",
            "agent_name": profile_payload["agent_name"],
            "profile": profile_payload,
            "tool_catalog": TOOL_CATALOG,
            "enabled_tool_ids": enabled_tool_ids,
            "curated_models": CURATED_CHAT_MODELS,
            "selected_model": selected_model,
        },
    )


@router.post("/settings", response_class=HTMLResponse)
async def settings_save(
    request: Request,
    db: AsyncClient = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
    name: str = Form(default=""),
    agent_name: str = Form(default=""),
    system_prompt: str = Form(default=""),
    enabled_tools: list[str] = Form(default=[]),
    default_model: str = Form(default=""),
):
    profile_payload: dict[str, object] = {
        "id": user_id,
        "name": name,
        "agent_name": agent_name,
        "agent_system_prompt": system_prompt,
    }
    if default_model in CURATED_CHAT_MODELS:
        profile_payload["default_model"] = default_model
    elif default_model:
        validate_model_selection(default_model, user_id=user_id)
    await upsert_profile(db, profile_payload)
    catalog_ids = {tool.id for tool in TOOL_CATALOG}
    selected_tool_ids = [tool_id for tool_id in enabled_tools if tool_id in catalog_ids]
    await replace_enabled_tools(db, user_id, selected_tool_ids)
    return templates.TemplateResponse(request, "partials/settings_save_status.html", {"request": request})
