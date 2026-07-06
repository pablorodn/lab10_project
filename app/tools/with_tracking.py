from collections.abc import Awaitable, Callable
from typing import Any

from supabase import AsyncClient

from app.db.queries.tool_calls import create_tool_call

ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


async def run_with_tracking(
    db: AsyncClient,
    session_id: str,
    tool_id: str,
    args: dict[str, Any],
    handler: ToolHandler,
    model_tool_call_id: str | None = None,
) -> dict[str, Any]:
    # Sin confirmacion no hay estado "pending" que mostrar en UI, asi que no hace
    # falta el INSERT optimista previo: se corre el handler primero y se escribe
    # un unico INSERT con el status/result final (executed o failed). Esto corta
    # a la mitad los round-trips a Supabase por cada tool call de bajo riesgo.
    try:
        result = await handler(args)
    except Exception:
        # Sin result_json en el fallo: igual que el comportamiento previo de
        # update_tool_call_status(..., "failed") sin result_payload.
        await create_tool_call(
            db=db,
            session_id=session_id,
            tool_name=tool_id,
            args=args,
            needs_confirmation=False,
            model_tool_call_id=model_tool_call_id,
            status="failed",
        )
        raise
    await create_tool_call(
        db=db,
        session_id=session_id,
        tool_name=tool_id,
        args=args,
        needs_confirmation=False,
        model_tool_call_id=model_tool_call_id,
        status="executed",
        result_json=result,
    )
    return result
