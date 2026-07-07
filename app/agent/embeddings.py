import asyncio

import httpx

from app.config import get_settings

EMBEDDING_MODEL = "openai/text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536

# Cache de proceso: mismo patron de lock + doble chequeo que create_server_client()
# (app/db/client.py) y el pool del checkpointer (app/agent/checkpointer.py). Antes se
# abria un httpx.AsyncClient nuevo -- y con el, una conexion TCP+TLS nueva -- en CADA
# llamada a generate_embedding(). Con el RTT de red medido en el diagnostico (~500ms),
# eso son ~1.5s de puro handshake por cada semantic_query de search_properties, cada
# flush de memoria y cada memory_injection. httpx.AsyncClient reutiliza conexiones
# (keep-alive) automaticamente entre requests hechos con la MISMA instancia, asi que
# cachear la instancia evita pagar ese handshake mas de una vez por proceso.
#
# No se cierra explicitamente en el shutdown de la app (a diferencia de un uso tipico
# de httpx.AsyncClient como context manager): httpx.AsyncClient si expone un
# aclose() bien definido, pero ningun otro recurso cacheado de este repo (el cliente
# Supabase de app/db/client.py, el pool de Postgres del checkpointer) tiene un hook de
# teardown en el lifespan de app/main.py (no hay codigo despues del `yield`) -- agregar
# uno solo para este cliente seria inconsistente con ese criterio ya establecido. El
# proceso libera los sockets al terminar de todas formas.
_embeddings_client: httpx.AsyncClient | None = None
_embeddings_client_lock = asyncio.Lock()


async def _get_embeddings_client() -> httpx.AsyncClient:
    global _embeddings_client
    if _embeddings_client is not None:
        return _embeddings_client
    async with _embeddings_client_lock:
        if _embeddings_client is None:
            _embeddings_client = httpx.AsyncClient(timeout=30)
    return _embeddings_client


async def generate_embedding(text: str) -> list[float]:
    settings = get_settings()
    client = await _get_embeddings_client()
    response = await client.post(
        "https://openrouter.ai/api/v1/embeddings",
        headers={
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "HTTP-Referer": "https://agents.local",
        },
        json={"model": EMBEDDING_MODEL, "input": text, "dimensions": EMBEDDING_DIMENSIONS},
    )
    response.raise_for_status()
    data = response.json()
    return data["data"][0]["embedding"]
