import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.model import create_compaction_model

logger = logging.getLogger(__name__)

CLASSIFIER_SYSTEM_PROMPT = (
    "Clasifica el siguiente mensaje de un usuario como 'episodic', 'semantic' o "
    "'procedural'.\n"
    "- 'episodic': un evento o interaccion puntual de esta conversacion, algo que "
    "paso ahora, sin valor de permanencia.\n"
    "- 'semantic': un hecho o preferencia estable del usuario (nombre, gustos, "
    "ocupacion, cosas que siguen siendo ciertas en el futuro).\n"
    "- 'procedural': como el usuario quiere que se le responda o se trabaje con el "
    "(estilo, formato, tono, workflow), y/o procedimientos o pasos concretos que el "
    "usuario ensena o pide recordar (una receta, un proceso tecnico propio).\n"
    "Responde unicamente con una palabra: 'episodic', 'semantic' o 'procedural'."
)


async def classify_memory_type(content: str) -> str:
    try:
        model = create_compaction_model()
        response = await model.ainvoke(
            [
                SystemMessage(content=CLASSIFIER_SYSTEM_PROMPT),
                HumanMessage(content=content),
            ]
        )
        label = str(getattr(response, "content", "")).strip().lower()
        if label not in ("episodic", "semantic", "procedural"):
            return "episodic"
        return label
    except Exception as exc:  # pragma: no cover - external services
        logger.warning(
            "Memory type classification skipped due to recoverable error.",
            extra={
                "event": "memory_classifier_error",
                "reason": str(exc),
            },
        )
        return "episodic"
