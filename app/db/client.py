import asyncio

from supabase import AsyncClient, create_async_client

from app.config import get_settings

# Cache de proceso: el service-role client no depende del usuario/request, así que se
# construye una sola vez y se reusa (antes se creaba un AsyncClient nuevo en cada llamada,
# incluyendo AuthMiddleware + Depends(get_db) en cada request). supabase.AsyncClient no
# expone un close()/aclose() unificado (solo sub-clientes internos como
# AsyncPostgrestClient.aclose() o el auth de gotrue tienen cierre parcial propio), por eso
# no se cierra explícitamente en el shutdown de la app: no hay un método soportado que
# garantice liberar todos sus recursos internos de una sola vez.
_server_client: AsyncClient | None = None
_server_client_lock = asyncio.Lock()


async def create_server_client() -> AsyncClient:
    global _server_client
    if _server_client is not None:
        return _server_client
    async with _server_client_lock:
        if _server_client is None:
            settings = get_settings()
            _server_client = await create_async_client(
                settings.supabase_url,
                settings.supabase_service_role_key,
            )
    return _server_client
