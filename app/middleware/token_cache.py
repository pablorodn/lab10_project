"""Caché en memoria de proceso para validaciones de access_token ya resueltas por
Supabase Auth. Evita una llamada de red a `get_user()` en cada request autenticado
-- el diagnóstico confirmó rutas públicas (~3ms) vs. rutas autenticadas (~3s,
hasta 11.2s), con esa llamada de red como único factor que las distingue.

La key es sha256(access_token), NUNCA el token crudo: si este dict terminara
volcado en un log o un dump de memoria, no debe haber tokens de sesión legibles
en texto plano.

TTL corto (60s) deliberado: los access tokens de Supabase ya expiran por si solos
en ~1h. Cachear 60s solo pospone hasta 60s la detección de una revocación
server-side (ej. el usuario cambia su password desde otro dispositivo/sesión) --
a cambio de eliminar una llamada de red de Supabase Auth en la enorme mayoría de
los requests. Un logout contra ESTE backend sí se refleja de inmediato, no tras
60s (ver invalidate_cached_token, usado por app/routers/auth.py).

Sin lock: la app corre en un único event loop de asyncio (no hay threads
concurrentes tocando este dict), y ninguna función de este módulo hace `await`
entre leer y escribir el dict -- por lo tanto dos requests concurrentes nunca
interleaven a mitad de una operación, y no hace falta sincronización explícita.
"""

import hashlib
import time

TOKEN_CACHE_TTL_SECONDS = 60
TOKEN_CACHE_MAX_ENTRIES = 1000

# hash(access_token) -> (user_id, expires_at monotonic)
_token_cache: dict[str, tuple[str, float]] = {}


def _hash_token(access_token: str) -> str:
    return hashlib.sha256(access_token.encode("utf-8")).hexdigest()


def get_cached_user_id(access_token: str) -> str | None:
    key = _hash_token(access_token)
    entry = _token_cache.get(key)
    if entry is None:
        return None
    user_id, expires_at = entry
    if time.monotonic() >= expires_at:
        del _token_cache[key]
        return None
    return user_id


def cache_token(access_token: str, user_id: str) -> None:
    _evict_expired_entries()
    if len(_token_cache) >= TOKEN_CACHE_MAX_ENTRIES:
        # Se superó el cap incluso después de evictar vencidas: es solo un
        # caché, reconstruirlo desde cero es barato (una llamada de red mas por
        # cada token no visto todavía), mucho más simple que implementar una
        # política LRU real para un caso que no debería darse en operación normal.
        _token_cache.clear()
    key = _hash_token(access_token)
    _token_cache[key] = (user_id, time.monotonic() + TOKEN_CACHE_TTL_SECONDS)


def invalidate_cached_token(access_token: str) -> None:
    _token_cache.pop(_hash_token(access_token), None)


def _evict_expired_entries() -> None:
    now = time.monotonic()
    expired_keys = [key for key, (_, expires_at) in _token_cache.items() if expires_at <= now]
    for key in expired_keys:
        del _token_cache[key]


def clear_token_cache() -> None:
    """Vacía el caché por completo. Uso previsto: aislar tests entre sí (varios
    archivos de test comparten el mismo token literal vía la fixture
    `auth_cookie`; sin este reset, un test podría heredar la entrada cacheada
    de otro test corrido segundos antes en el mismo proceso de pytest)."""
    _token_cache.clear()
