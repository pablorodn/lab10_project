"""Cliente Supabase de SOLO LECTURA hacia un proyecto Supabase separado, dedicado
exclusivamente a datos de propiedades (tablas `properties` / `property_embeddings`, ver
migrations/properties_db/). Nunca debe usarse con una key distinta a la anon key: la
seguridad de exponer esa key depende de que ese proyecto tenga RLS activo y una policy de
solo-SELECT para el rol `anon` (ver migrations/properties_db/00003_rls_readonly_anon.sql).
"""

import asyncio

from supabase import AsyncClient, create_async_client

from app.config import get_settings

# Mismo patrón de cache de proceso que create_server_client() en app/db/client.py.
_properties_client: AsyncClient | None = None
_properties_client_lock = asyncio.Lock()


async def create_properties_client() -> AsyncClient:
    global _properties_client
    if _properties_client is not None:
        return _properties_client
    async with _properties_client_lock:
        if _properties_client is None:
            settings = get_settings()
            if not settings.is_properties_db_configured:
                raise RuntimeError(
                    "PROPERTIES_SUPABASE_URL / PROPERTIES_SUPABASE_ANON_KEY no configuradas."
                )
            # is_properties_db_configured ya garantiza que ambos son truthy; narrowing
            # explícito para mypy, que no propaga tipos a través de la property.
            assert settings.properties_supabase_url and settings.properties_supabase_anon_key
            _properties_client = await create_async_client(
                settings.properties_supabase_url,
                settings.properties_supabase_anon_key,
            )
    return _properties_client
