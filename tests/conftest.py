import os

import pytest

from app.middleware.token_cache import clear_token_cache

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "anon")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "service")
os.environ.setdefault("DATABASE_URL", "postgres://postgres:postgres@localhost:5432/postgres")
os.environ.setdefault("OPENROUTER_API_KEY", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-test-suite-only")


@pytest.fixture(autouse=True)
def _reset_token_cache():
    # Muchos tests comparten el mismo token literal via la fixture auth_cookie
    # ("test-token"). El caché de AuthMiddleware (app/middleware/token_cache.py)
    # es estado global de proceso con TTL de 60s -- sin este reset, un test
    # heredaria silenciosamente la entrada cacheada de otro test corrido segundos
    # antes en el mismo proceso de pytest, saltandose el mock que ese test
    # instaló para validate_access_token/create_server_client.
    clear_token_cache()
    yield
    clear_token_cache()


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def auth_cookie() -> dict[str, str]:
    return {"sb-access-token": "test-token"}


@pytest.fixture
def patch_auth_middleware(monkeypatch):
    class _FakeUser:
        def model_dump(self):
            return {"id": "user-1"}

    class _FakeAuth:
        async def get_user(self, _token: str):
            class _User:
                user = _FakeUser()

            return _User()

    class _FakeClient:
        auth = _FakeAuth()

    async def _fake_create_server_client():
        return _FakeClient()

    monkeypatch.setattr("app.middleware.auth.create_server_client", _fake_create_server_client)
    return _fake_create_server_client
