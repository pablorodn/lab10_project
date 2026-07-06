from typing import Any

from pydantic import BaseModel
from supabase import AsyncClient


class Profile(BaseModel):
    id: str
    name: str | None = None
    timezone: str | None = None
    language: str | None = None
    agent_name: str | None = None
    agent_system_prompt: str | None = None
    default_model: str | None = None
    onboarding_completed: bool = False


async def get_profile(db: AsyncClient, user_id: str) -> Profile | None:
    result = await db.table("profiles").select("*").eq("id", user_id).limit(1).execute()
    if not result.data:
        return None
    return Profile(**result.data[0])


async def upsert_profile(db: AsyncClient, payload: dict[str, Any]) -> Profile:
    result = await db.table("profiles").upsert(payload).execute()
    return Profile(**result.data[0])
