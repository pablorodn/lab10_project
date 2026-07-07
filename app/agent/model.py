import logging
from collections.abc import Sequence
from typing import Any

from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI

from app.config import get_settings

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
PRIMARY_CHAT_MODEL = "google/gemini-2.5-flash"
FALLBACK_CHAT_MODEL = "openai/gpt-4o-mini"
CHAT_TIMEOUT_SECONDS = 20.0

# Lista curada del selector de modelo (Fase 10). Única fuente de verdad hasta
# futura sesión dedicada de documentación.
CURATED_CHAT_MODELS: tuple[str, str] = (PRIMARY_CHAT_MODEL, FALLBACK_CHAT_MODEL)

logger = logging.getLogger(__name__)


def validate_model_selection(requested_model: str | None, *, user_id: str) -> str:
    if requested_model in CURATED_CHAT_MODELS:
        return requested_model
    if requested_model:
        logger.warning(
            "Requested chat model is not in the curated list; using default.",
            extra={
                "event": "model_selection_rejected",
                "requested_model": requested_model,
                "fallback_model": PRIMARY_CHAT_MODEL,
                "user_id": user_id,
            },
        )
    return PRIMARY_CHAT_MODEL


def create_chat_model(
    model_name: str = PRIMARY_CHAT_MODEL, tool_schemas: list[dict[str, Any]] | None = None
) -> Runnable:
    settings = get_settings()
    model = ChatOpenAI(
        model=model_name,
        temperature=0.2,
        max_tokens=1000,
        timeout=CHAT_TIMEOUT_SECONDS,
        # L2 (tradeoff documentado, sin cambio de comportamiento en esta ronda):
        # max_retries=0 hace que CUALQUIER error transitorio del modelo primario
        # (incluido un 429 de rate limit de OpenRouter) caiga directo a
        # ainvoke_chat_with_fallback() usando FALLBACK_CHAT_MODEL, en vez de
        # reintentar con backoff corto sobre el mismo modelo. Es intencional:
        # prioriza latencia (fallback rapido) sobre "insistir" en el primario.
        # La contra es que un burst breve de 429 empuja todo el trafico al
        # modelo de fallback aunque el primario se hubiera recuperado enseguida.
        # Un backoff corto especifico para 429 quedo fuera de alcance de esta
        # ronda (Fase 3) — evaluar si en la practica los 429 de OpenRouter son
        # frecuentes antes de invertir en eso.
        max_retries=0,
        openai_api_key=settings.openrouter_api_key,
        openai_api_base=OPENROUTER_BASE_URL,
        default_headers={"HTTP-Referer": "https://agents.local"},
    )  # type: ignore[call-arg]
    if tool_schemas:
        return model.bind_tools(tool_schemas)
    return model


def create_compaction_model(max_tokens: int | None = 2000) -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        model="google/gemini-2.5-flash",
        temperature=0.1,
        max_tokens=max_tokens,
        openai_api_key=settings.openrouter_api_key,
        openai_api_base=OPENROUTER_BASE_URL,
        default_headers={"HTTP-Referer": "https://agents.local"},
    )  # type: ignore[call-arg]


async def ainvoke_chat_with_fallback(
    messages: Sequence[Any],
    primary_model: str = PRIMARY_CHAT_MODEL,
    tool_schemas: list[dict[str, Any]] | None = None,
) -> AIMessage:
    fallback_model = FALLBACK_CHAT_MODEL if primary_model != FALLBACK_CHAT_MODEL else PRIMARY_CHAT_MODEL
    primary = create_chat_model(primary_model, tool_schemas)
    try:
        # No se envuelve en asyncio.wait_for: sería redundante con el timeout=CHAT_TIMEOUT_SECONDS
        # ya fijado en create_chat_model. A diferencia de la llamada primaria, la llamada de
        # fallback (mas abajo) nunca tuvo un wait_for propio, asi que el timeout del cliente es
        # lo unico que la acota — eliminarlo la dejaria sin limite de tiempo.
        result = await primary.ainvoke(messages)
        if isinstance(result, AIMessage):
            return result
        return AIMessage(content=str(getattr(result, "content", "")))
    except Exception as exc:
        logger.warning(
            "Primary chat model failed; using fallback.",
            extra={
                "event": "chat_model_fallback",
                "reason": str(exc),
                "primary_model": primary_model,
                "fallback_model": fallback_model,
            },
        )

    fallback = create_chat_model(fallback_model, tool_schemas)
    result = await fallback.ainvoke(messages)
    if isinstance(result, AIMessage):
        return result
    return AIMessage(content=str(getattr(result, "content", "")))
