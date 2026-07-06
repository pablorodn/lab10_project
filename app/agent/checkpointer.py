import asyncio
import logging
from urllib.parse import urlparse

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool

from app.config import get_settings

logger = logging.getLogger(__name__)

# No hay un patrón de configuración numérica equivalente en app/config.py hoy
# (Settings no tiene campos de tuning de pool), así que estos tamaños quedan
# hardcodeados. min_size=1 evita conexiones ociosas en dev; max_size=10 acota
# la concurrencia de checkpoints sin agotar el límite de conexiones de Postgres.
CHECKPOINTER_POOL_MIN_SIZE = 1
CHECKPOINTER_POOL_MAX_SIZE = 10

# M2 (pendiente de decision consciente, no tocar sin discutirlo primero):
# LangGraph con este checkpointer usa durability="async" (el default en la
# version instalada) — escribe un checkpoint completo por superstep/nodo, no
# solo al final del run. Un turno sin tools ya son ~3 escrituras (memory_injection
# y compaction en paralelo + agent); uno con una ida y vuelta de tools son ~5.
# Como los bloques de adjunto (imagen en base64) viven dentro de HumanMessage.content
# en `messages`, cada una de esas escrituras re-serializa el mismo blob mientras
# el mensaje no se compacte (compaction dispara recien al 80% de la ventana de
# contexto). Esto es exactamente la misma razon por la que se elimino el soporte
# de PDF (docs/implementation-summary.md) — con imagenes el problema es menor
# (cap de 5MB) pero existe igual. LangGraph 1.2.7 expone durability="exit" para
# persistir solo al final del run, lo cual reduciria el write amplification, pero
# no se evaluo si eso rompe la semantica de interrupt()/Command(resume=...) que
# el flujo de HITL de este repo depende (necesita un checkpoint justo antes de
# la pausa). No cambiar esto sin decidir conscientemente el tradeoff con el equipo.

_saver: AsyncPostgresSaver | None = None
# Antes era una única AsyncConnection cacheada: bajo concurrencia real (2+ chats
# simultáneos) serializaba todas las lecturas/escrituras de checkpoint de todos
# los usuarios sobre la misma sesión de Postgres. Un pool permite que cada turno
# concurrente tome su propia conexión.
_pool: AsyncConnectionPool[AsyncConnection[DictRow]] | None = None
_lock = asyncio.Lock()


async def get_checkpointer() -> AsyncPostgresSaver:
    global _saver
    global _pool
    if _saver is not None:
        return _saver
    async with _lock:
        if _saver is None:
            settings = get_settings()
            try:
                dsn = settings.normalized_database_url
                parsed = urlparse(dsn)
                if not parsed.scheme or not parsed.hostname:
                    raise ValueError("DATABASE_URL missing scheme or hostname")
                _pool = AsyncConnectionPool(
                    dsn,
                    min_size=CHECKPOINTER_POOL_MIN_SIZE,
                    max_size=CHECKPOINTER_POOL_MAX_SIZE,
                    kwargs={
                        "autocommit": True,
                        "prepare_threshold": 0,
                        "row_factory": dict_row,
                    },
                    open=False,
                )
                await _pool.open()
                postgres_saver = AsyncPostgresSaver(_pool)
                await postgres_saver.setup()
                _saver = postgres_saver
            except Exception as exc:  # pragma: no cover - depends on local infra
                logger.error(
                    "Postgres checkpointer initialization failed.",
                    extra={
                        "event": "checkpointer_init_error",
                        "reason": str(exc),
                        "database_host": settings.database_host,
                    },
                )
                raise RuntimeError("Postgres checkpointer unavailable. Verify DATABASE_URL and database connectivity.") from exc
    return _saver
