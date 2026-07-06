import logging

from langchain_core.messages import RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES

from app.agent.compaction import (
    CIRCUIT_BREAKER_LIMIT,
    llm_compact,
    microcompact,
    should_compact,
)
from app.agent.state import AgentState

logger = logging.getLogger(__name__)

# Cuantas veces se toma la rama microcompact con el circuito abierto antes de
# volver a intentar llm_compact ("half-open"). should_compact() solo deja
# pasar el turno a este nodo cuando el historial ya esta cerca del limite de
# contexto, asi que este contador cuenta invocaciones reales de compactacion
# (no cualquier turno de chat). 5 es un punto medio deliberado: suficientemente
# bajo para recuperar la calidad de resumen LLM en minutos/pocas horas de uso
# normal tras una caida transitoria del modelo de compactacion, y
# suficientemente alto para no volver a pagar el costo de un intento fallido
# (y su latencia) en cada una de esas invocaciones mientras la caida persiste.
COMPACTION_BREAKER_RETRY_INTERVAL = 5


def _replace_messages(messages: list) -> list:
    return [RemoveMessage(id=REMOVE_ALL_MESSAGES), *messages]


async def compaction_node(state: AgentState) -> dict:
    messages = state["messages"]
    if not should_compact(messages):
        return {}

    failure_count = state.get("compaction_failure_count", 0)
    compaction_count = state.get("compaction_count", 0)
    breaker_skips = state.get("compaction_breaker_skips", 0)

    breaker_open = failure_count >= CIRCUIT_BREAKER_LIMIT
    half_open_retry = breaker_open and breaker_skips >= COMPACTION_BREAKER_RETRY_INTERVAL

    if breaker_open and not half_open_retry:
        compacted = microcompact(messages)
        return {
            "messages": _replace_messages(compacted),
            "compaction_count": compaction_count + 1,
            "compaction_failure_count": failure_count,
            "compaction_breaker_skips": breaker_skips + 1,
        }

    try:
        compacted = await llm_compact(messages)
        return {
            "messages": _replace_messages(compacted),
            "compaction_count": compaction_count + 1,
            "compaction_failure_count": 0,
            "compaction_breaker_skips": 0,
        }
    except Exception as exc:
        logger.warning(
            "LLM compaction failed; falling back to microcompact.",
            extra={
                "event": "compaction_llm_failed",
                "reason": str(exc),
                "session_id": state.get("session_id"),
                "failure_count": failure_count + 1,
            },
        )
        compacted = microcompact(messages)
        return {
            "messages": _replace_messages(compacted),
            "compaction_count": compaction_count + 1,
            "compaction_failure_count": failure_count + 1,
            "compaction_breaker_skips": 0,
        }
