import asyncio
from datetime import datetime, timezone

from pydantic import BaseModel
from supabase import AsyncClient

# Lock por usuario para serializar get_or_create_active_session (mas abajo) y
# cerrar una condicion de carrera real: get_active_session (check) y create_session
# (insert) no son atomicos entre si, asi que dos GET /chat casi simultaneas del mismo
# usuario (frecuente en el entorno de red lenta actual, ~500ms de RTT, ante cualquier
# refresh a mitad de carga) pueden ver ambas "no hay sesion activa" y ambas crear una,
# duplicando la sesion. NO se puede resolver con un unique constraint en la DB porque
# tener multiples sesiones activas por usuario es legitimo (boton "+ Nueva sesion",
# que usa create_session() directo, sin este lock).
#
# Limitacion conocida: este es un lock de PROCESO UNICO (dict en memoria de un solo
# worker uvicorn) -- alcanza para el deploy actual (un unico worker). Si en el futuro
# se corre con multiples workers/instancias, este dict deja de servir (cada proceso
# tendria el suyo) y haria falta un advisory lock de Postgres
# (pg_advisory_xact_lock, hasheando user_id a bigint) para serializar entre procesos.
# No implementado aca -- queda anotado para cuando aplique.
_user_session_locks: dict[str, asyncio.Lock] = {}
USER_SESSION_LOCKS_MAX_ENTRIES = 1000


def _get_user_session_lock(user_id: str) -> asyncio.Lock:
    lock = _user_session_locks.get(user_id)
    if lock is not None:
        return lock
    _evict_unlocked_session_locks_if_over_cap()
    lock = asyncio.Lock()
    _user_session_locks[user_id] = lock
    return lock


def _evict_unlocked_session_locks_if_over_cap() -> None:
    if len(_user_session_locks) < USER_SESSION_LOCKS_MAX_ENTRIES:
        return
    # A diferencia de un cache de datos (ej. app/middleware/token_cache.py), ac
    # NO se puede vaciar el dict entero: un Lock con locked() == True significa que
    # hay un request en vuelo usandolo AHORA MISMO -- borrarlo le daria a un caller
    # nuevo un asyncio.Lock() distinto sin que el holder actual se entere, rompiendo
    # justo la exclusion mutua que este modulo existe para garantizar. Solo se
    # evictan los locks libres.
    for uid in [uid for uid, lock in _user_session_locks.items() if not lock.locked()]:
        del _user_session_locks[uid]


class AgentSession(BaseModel):
    id: str
    user_id: str
    channel: str
    status: str
    last_used_at: str | None = None
    title: str | None = None
    budget_tokens_used: int
    budget_tokens_limit: int
    created_at: str
    updated_at: str


async def list_sessions(db: AsyncClient, user_id: str, channel: str = "web") -> list[AgentSession]:
    result = (
        await db.table("agent_sessions")
        .select("*")
        .eq("user_id", user_id)
        .eq("channel", channel)
        .eq("status", "active")
        .order("created_at", desc=True)
        .limit(10)
        .execute()
    )
    return [AgentSession(**row) for row in result.data]


async def get_active_session(
    db: AsyncClient, user_id: str, channel: str
) -> AgentSession | None:
    result = (
        await db.table("agent_sessions")
        .select("*")
        .eq("user_id", user_id)
        .eq("channel", channel)
        .eq("status", "active")
        .order("last_used_at", desc=True)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return AgentSession(**result.data[0])


async def create_session(db: AsyncClient, user_id: str, channel: str = "web") -> AgentSession:
    payload = {
        "user_id": user_id,
        "channel": channel,
        "status": "active",
        "last_used_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await db.table("agent_sessions").insert(payload).execute()
    return AgentSession(**result.data[0])


async def get_or_create_active_session(
    db: AsyncClient, user_id: str, channel: str
) -> AgentSession:
    # Lock ANTES de get_active_session y hasta despues de create_session: dos
    # llamadas concurrentes del mismo usuario se serializan aca. La segunda espera a
    # que la primera termine (cree o no una sesion) y su propio get_active_session ya
    # encuentra la que la primera acaba de crear, en vez de duplicarla.
    async with _get_user_session_lock(user_id):
        current = await get_active_session(db, user_id, channel)
        if current:
            return current
        return await create_session(db, user_id, channel)


async def touch_session(db: AsyncClient, session_id: str) -> None:
    await (
        db.table("agent_sessions")
        .update({"last_used_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", session_id)
        .execute()
    )


async def get_session_by_id(db: AsyncClient, session_id: str) -> AgentSession | None:
    result = await db.table("agent_sessions").select("*").eq("id", session_id).limit(1).execute()
    if not result.data:
        return None
    return AgentSession(**result.data[0])


async def update_session_title(db: AsyncClient, session_id: str, title: str) -> bool:
    result = (
        await db.table("agent_sessions")
        .update({"title": title})
        .eq("id", session_id)
        .is_("title", "null")
        .execute()
    )
    return bool(result.data)


async def archive_session(db: AsyncClient, session_id: str) -> None:
    await db.table("agent_sessions").update({"status": "archived"}).eq("id", session_id).execute()


async def delete_session(db: AsyncClient, session_id: str) -> None:
    await db.table("agent_sessions").delete().eq("id", session_id).execute()
