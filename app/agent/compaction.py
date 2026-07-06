import logging

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from app.agent.model import create_compaction_model

logger = logging.getLogger(__name__)

CHARS_PER_TOKEN = 4
CONTEXT_WINDOW_TOKENS = 128_000
COMPACTION_THRESHOLD = 0.8
COMPACTION_TAIL_SIZE = 10
CIRCUIT_BREAKER_LIMIT = 3

COMPACTION_SECTIONS_PROMPT = """Resume el historial de conversación en español usando exactamente estas secciones markdown:
## Contexto
## Acciones y herramientas
## Decisiones y resultados
## Pendiente
Sé conciso. No inventes información."""


def estimate_tokens(messages: list[BaseMessage]) -> int:
    total_chars = sum(len(str(msg.content)) for msg in messages)
    return total_chars // CHARS_PER_TOKEN


def should_compact(messages: list[BaseMessage]) -> bool:
    return estimate_tokens(messages) >= int(CONTEXT_WINDOW_TOKENS * COMPACTION_THRESHOLD)


def microcompact(messages: list[BaseMessage]) -> list[BaseMessage]:
    if len(messages) <= COMPACTION_TAIL_SIZE:
        return messages
    return messages[-COMPACTION_TAIL_SIZE:]


def split_head_and_tail(messages: list[BaseMessage]) -> tuple[list[BaseMessage], list[BaseMessage]]:
    if len(messages) <= COMPACTION_TAIL_SIZE:
        return [], list(messages)
    return messages[:-COMPACTION_TAIL_SIZE], messages[-COMPACTION_TAIL_SIZE:]


def _format_messages_for_summary(messages: list[BaseMessage]) -> str:
    lines: list[str] = []
    for message in messages:
        role = message.__class__.__name__
        content = str(message.content)
        lines.append(f"{role}: {content}")
    return "\n\n".join(lines)


async def llm_compact(messages: list[BaseMessage]) -> list[BaseMessage]:
    head, tail = split_head_and_tail(messages)
    if not head:
        return list(messages)

    transcript = _format_messages_for_summary(head)
    model = create_compaction_model()
    result = await model.ainvoke(
        [
            SystemMessage(content=COMPACTION_SECTIONS_PROMPT),
            HumanMessage(content=f"Historial a compactar:\n\n{transcript}"),
        ]
    )
    summary_text = str(getattr(result, "content", "")).strip()
    if not summary_text:
        raise RuntimeError("Compaction model returned empty summary")

    summary_message = SystemMessage(content=f"[RESUMEN DE CONTEXTO COMPACTADO]\n\n{summary_text}")
    return [summary_message, *tail]
