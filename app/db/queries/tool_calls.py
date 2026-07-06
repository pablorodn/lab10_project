from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel
from supabase import AsyncClient


class ToolCall(BaseModel):
    id: str
    session_id: str
    tool_name: str
    status: str
    requires_confirmation: bool = False
    model_tool_call_id: str | None = None
    result_json: dict[str, Any] | None = None
    arguments_json: dict[str, Any] | None = None


async def create_tool_call(
    db: AsyncClient,
    session_id: str,
    tool_name: str,
    args: dict[str, Any],
    needs_confirmation: bool,
    model_tool_call_id: str | None,
    *,
    status: str | None = None,
    result_json: dict[str, Any] | None = None,
) -> ToolCall:
    """Inserta una fila en tool_calls.

    `status`/`result_json` permiten a run_with_tracking (rama sin confirmacion)
    escribir el estado final (executed/failed) en un unico INSERT, en vez del
    patron INSERT-optimista-luego-UPDATE. La rama con confirmacion sigue usando
    los defaults (needs_confirmation=True -> status="pending_confirmation" sin
    result_json), sin cambio de comportamiento.
    """
    resolved_status = status or ("pending_confirmation" if needs_confirmation else "executed")
    payload: dict[str, Any] = {
        "session_id": session_id,
        "tool_name": tool_name,
        "arguments_json": args,
        "status": resolved_status,
        "requires_confirmation": needs_confirmation,
        "model_tool_call_id": model_tool_call_id,
    }
    if result_json is not None:
        payload["result_json"] = result_json
    if resolved_status in {"executed", "failed"}:
        payload["finished_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.table("tool_calls").insert(payload).execute()
    return ToolCall(**result.data[0])


async def update_tool_call_status(
    db: AsyncClient,
    tool_call_id: str,
    status: str,
    result_payload: dict[str, Any] | None = None,
) -> None:
    update_data: dict[str, Any] = {"status": status}
    if result_payload is not None:
        update_data["result_json"] = result_payload
    if status in {"rejected", "executed", "failed"}:
        update_data["finished_at"] = datetime.now(timezone.utc).isoformat()
    await db.table("tool_calls").update(update_data).eq("id", tool_call_id).execute()


async def get_pending_tool_call(db: AsyncClient, tool_call_id: str) -> ToolCall | None:
    result = (
        await db.table("tool_calls")
        .select("*")
        .eq("id", tool_call_id)
        .eq("status", "pending_confirmation")
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return ToolCall(**result.data[0])


async def find_or_create_pending_tool_call(
    db: AsyncClient,
    session_id: str,
    tool_name: str,
    args: dict[str, Any],
    model_tool_call_id: str,
) -> ToolCall:
    existing = (
        await db.table("tool_calls")
        .select("*")
        .eq("session_id", session_id)
        .eq("model_tool_call_id", model_tool_call_id)
        .eq("status", "pending_confirmation")
        .limit(1)
        .execute()
    )
    if existing.data:
        return ToolCall(**existing.data[0])
    return await create_tool_call(
        db=db,
        session_id=session_id,
        tool_name=tool_name,
        args=args,
        needs_confirmation=True,
        model_tool_call_id=model_tool_call_id,
    )


async def has_pending_confirmation_for_session(db: AsyncClient, session_id: str) -> bool:
    result = (
        await db.table("tool_calls")
        .select("id")
        .eq("session_id", session_id)
        .eq("status", "pending_confirmation")
        .limit(1)
        .execute()
    )
    return bool(result.data)
