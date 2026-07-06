import asyncio
import logging

from supabase import AsyncClient

from app.agent.embeddings import generate_embedding
from app.agent.memory_classifier import classify_memory_type
from app.db.queries.memories import save_memory
from app.db.queries.messages import get_last_user_message
from app.services.memory_policy import can_store_memory

logger = logging.getLogger(__name__)


async def flush_session_memory(db: AsyncClient, user_id: str, session_id: str) -> None:
    try:
        last_user_message = await get_last_user_message(db, session_id)
        if last_user_message is None:
            return
        latest = (last_user_message.content or "").strip()
        if not latest:
            return
        if not can_store_memory(latest):
            return
        memory_type, embedding = await asyncio.gather(
            classify_memory_type(latest), generate_embedding(latest)
        )
        await save_memory(db, user_id=user_id, memory_type=memory_type, content=latest, embedding=embedding)
    except Exception as exc:  # pragma: no cover - external services
        logger.warning(
            "Memory flush skipped due to recoverable error.",
            extra={
                "event": "memory_flush_error",
                "reason": str(exc),
                "user_id": user_id,
                "session_id": session_id,
            },
        )
