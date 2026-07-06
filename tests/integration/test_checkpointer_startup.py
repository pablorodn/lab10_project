from types import SimpleNamespace

import pytest

from app.agent import checkpointer as checkpointer_module


@pytest.mark.anyio
async def test_checkpointer_uses_postgres_pool_when_connection_is_available(monkeypatch):
    calls: dict[str, object] = {}

    class _FakePostgresSaver:
        def __init__(self, pool):
            calls["pool"] = pool

        async def setup(self):
            calls["setup"] = True

    class _FakePool:
        def __init__(self, dsn, **kwargs):
            calls["dsn"] = dsn
            calls["pool_kwargs"] = kwargs

        async def open(self):
            calls["opened"] = True

    def _fake_settings():
        return SimpleNamespace(
            normalized_database_url="postgres://postgres:postgres@localhost:5432/postgres",
            database_host="localhost",
        )

    monkeypatch.setattr(checkpointer_module, "AsyncPostgresSaver", _FakePostgresSaver)
    monkeypatch.setattr(checkpointer_module, "AsyncConnectionPool", _FakePool)
    monkeypatch.setattr(checkpointer_module, "get_settings", _fake_settings)
    checkpointer_module._saver = None
    checkpointer_module._pool = None

    saver = await checkpointer_module.get_checkpointer()

    assert isinstance(saver, _FakePostgresSaver)
    assert calls["setup"] is True
    assert calls["opened"] is True
    assert calls["dsn"] == "postgres://postgres:postgres@localhost:5432/postgres"
    assert calls["pool_kwargs"]["min_size"] == checkpointer_module.CHECKPOINTER_POOL_MIN_SIZE
    assert calls["pool_kwargs"]["max_size"] == checkpointer_module.CHECKPOINTER_POOL_MAX_SIZE


@pytest.mark.anyio
async def test_checkpointer_fails_loudly_on_connection_error(monkeypatch):
    class _FailingPool:
        def __init__(self, *_args, **_kwargs):
            pass

        async def open(self):
            raise RuntimeError("cannot connect")

    def _fake_settings():
        return SimpleNamespace(
            normalized_database_url="postgres://postgres:postgres@localhost:5432/postgres",
            database_host="localhost",
        )

    monkeypatch.setattr(checkpointer_module, "AsyncConnectionPool", _FailingPool)
    monkeypatch.setattr(checkpointer_module, "get_settings", _fake_settings)
    checkpointer_module._saver = None
    checkpointer_module._pool = None

    with pytest.raises(RuntimeError, match="Postgres checkpointer unavailable"):
        await checkpointer_module.get_checkpointer()
