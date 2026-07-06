from supabase import AsyncClient


async def list_enabled_tool_ids(db: AsyncClient, user_id: str) -> list[str]:
    result = await db.table("user_tool_settings").select("tool_id,enabled").eq("user_id", user_id).execute()
    return [row["tool_id"] for row in result.data if row.get("enabled")]


async def replace_enabled_tools(db: AsyncClient, user_id: str, tool_ids: list[str]) -> None:
    await db.table("user_tool_settings").delete().eq("user_id", user_id).execute()
    payload = [{"user_id": user_id, "tool_id": t, "enabled": True} for t in tool_ids]
    if payload:
        await db.table("user_tool_settings").insert(payload).execute()
