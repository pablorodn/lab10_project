from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from supabase import AsyncClient

from app.db.queries.profiles import get_profile, upsert_profile
from app.db.queries.tools import replace_enabled_tools
from app.dependencies import get_current_user_id, get_db
from app.services.onboarding_session import get_onboarding_data, update_onboarding_data
from app.tools.catalog import TOOL_CATALOG

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
STEPS = ["onboarding/step_profile.html", "onboarding/step_agent.html", "onboarding/step_tools.html", "onboarding/step_review.html"]


def _ctx(request: Request, current_step: int) -> dict:
    data = get_onboarding_data(request.session)
    return {
        "request": request,
        "current_step": current_step,
        "step_partial": STEPS[current_step],
        "data": data,
        "tool_catalog": TOOL_CATALOG,
        "timezones": ["America/Bogota", "UTC", "America/Mexico_City"],
    }


@router.get("/onboarding", response_class=HTMLResponse)
async def onboarding(
    request: Request,
    db: AsyncClient = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    profile = await get_profile(db, user_id)
    if profile and profile.onboarding_completed:
        return RedirectResponse(url="/chat", status_code=307)
    return templates.TemplateResponse(request, "onboarding/wizard.html", _ctx(request, 0))


@router.get("/onboarding/step/{step}", response_class=HTMLResponse)
async def onboarding_step(
    step: int,
    request: Request,
    db: AsyncClient = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    profile = await get_profile(db, user_id)
    if profile and profile.onboarding_completed:
        return RedirectResponse(url="/chat", status_code=307)
    return templates.TemplateResponse(request, "onboarding/wizard.html", _ctx(request, max(0, min(step, 3))))


@router.post("/onboarding/step/{step}", response_class=HTMLResponse)
async def onboarding_step_post(
    step: int,
    request: Request,
    db: AsyncClient = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
    name: str | None = Form(default=None),
    timezone: str | None = Form(default=None),
    language: str | None = Form(default=None),
    agent_name: str | None = Form(default=None),
    system_prompt: str | None = Form(default=None),
    enabled_tools: list[str] = Form(default=[]),
):
    profile = await get_profile(db, user_id)
    if profile and profile.onboarding_completed:
        return RedirectResponse(url="/chat", status_code=307)
    payload: dict[str, object] = {
        k: v
        for k, v in {
            "name": name,
            "timezone": timezone,
            "language": language,
            "agent_name": agent_name,
            "agent_system_prompt": system_prompt,
        }.items()
        if v is not None
    }
    if step == 2:
        payload["enabled_tools"] = enabled_tools
    update_onboarding_data(request.session, payload)
    next_step = max(0, min(step + 1, 3))
    return templates.TemplateResponse(request, "onboarding/wizard.html", _ctx(request, next_step))


@router.post("/onboarding/finish", response_class=HTMLResponse)
async def onboarding_finish(
    request: Request,
    db: AsyncClient = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    data = get_onboarding_data(request.session)
    await upsert_profile(
        db,
        {
            "id": user_id,
            "name": data.get("name", ""),
            "timezone": data.get("timezone", "UTC"),
            "language": data.get("language", "es"),
            "agent_name": data.get("agent_name", "Agente"),
            "agent_system_prompt": data.get("agent_system_prompt", ""),
            "onboarding_completed": True,
        },
    )
    selected_tools = data.get("enabled_tools", [])
    catalog_ids = {tool.id for tool in TOOL_CATALOG}
    enabled_tool_ids = [tool_id for tool_id in selected_tools if tool_id in catalog_ids]
    await replace_enabled_tools(db, user_id, enabled_tool_ids)
    request.session.pop("onboarding_data", None)
    response = HTMLResponse(status_code=200)
    response.headers["HX-Redirect"] = "/chat"
    return response
