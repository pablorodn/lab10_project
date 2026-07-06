from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from supabase import AsyncClient

from app.db.queries.profiles import get_profile
from app.dependencies import get_current_user_id, get_db

router = APIRouter()


@router.get("/")
async def index(
    request: Request,
    db: AsyncClient = Depends(get_db),
    user_id: str = Depends(get_current_user_id),
):
    _ = request
    profile = await get_profile(db, user_id)
    if not profile or not profile.onboarding_completed:
        return RedirectResponse("/onboarding", status_code=307)
    return RedirectResponse("/chat", status_code=307)
