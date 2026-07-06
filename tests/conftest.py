import os

import pytest

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "anon")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "service")
os.environ.setdefault("DATABASE_URL", "postgres://postgres:postgres@localhost:5432/postgres")
os.environ.setdefault("OPENROUTER_API_KEY", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-test-suite-only")


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
