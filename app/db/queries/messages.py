from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel
from supabase import AsyncClient


class AgentMessage(BaseModel):
    id: str
    session_id: str
    role: str
    content: str
    structured_payload: dict[str, Any] | None = None


async def add_message(
    db: AsyncClient,
    session_id: str,
    role: str,
    content: str,
    structured_payload: dict[str, Any] | None = None,
) -> AgentMessage:
    payload: dict[str, Any] = {
        "session_id": session_id,
        "role": role,
        "content": content,
        "structured_payload": structured_payload,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await db.table("agent_messages").insert(payload).execute()
    return AgentMessage(**result.data[0])


async def get_session_messages(db: AsyncClient, session_id: str) -> list[AgentMessage]:
    result = (
        await db.table("agent_messages")
        .select("*")
        .eq("session_id", session_id)
        .order("created_at", desc=False)
        .execute()
    )
    return [AgentMessage(**row) for row in result.data]


async def get_first_user_message_with_content(
    db: AsyncClient, session_id: str
) -> AgentMessage | None:
    """Primer mensaje de rol 'user' con contenido no vacío (usado para el título de sesión)."""
    result = (
        await db.table("agent_messages")
        .select("*")
        .eq("session_id", session_id)
        .eq("role", "user")
        .neq("content", "")
        .order("created_at", desc=False)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return AgentMessage(**result.data[0])


async def get_last_user_message(db: AsyncClient, session_id: str) -> AgentMessage | None:
    """Último mensaje de rol 'user' de la sesión, sin filtrar por contenido: el
    llamador (flush_session_memory) decide si ese mensaje puntual tiene contenido
    utilizable, igual que antes cuando filtraba en Python sobre la lista completa."""
    result = (
        await db.table("agent_messages")
        .select("*")
        .eq("session_id", session_id)
        .eq("role", "user")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return AgentMessage(**result.data[0])


async def clear_session_messages(db: AsyncClient, session_id: str) -> None:
    await db.table("agent_messages").delete().eq("session_id", session_id).execute()
