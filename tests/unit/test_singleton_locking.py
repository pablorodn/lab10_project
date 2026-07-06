import asyncio

from app.agent import checkpointer
from app.agent import graph as graph_module
from app.db import client as client_module


async def test_create_server_client_concurrent_calls_build_client_once(monkeypatch):
    client_module._server_client = None
    sentinel = object()
    call_count = 0

    async def _fake_create_async_client(_url, _key):
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.05)
        return sentinel

    monkeypatch.setattr(client_module, "create_async_client", _fake_create_async_client)

    results = await asyncio.gather(*[client_module.create_server_client() for _ in range(5)])

    assert call_count == 1
    assert all(result is sentinel for result in results)


async def test_create_server_client_sequential_calls_reuse_same_instance(monkeypatch):
    client_module._server_client = None
    call_count = 0

    async def _fake_create_async_client(_url, _key):
        nonlocal call_count
        call_count += 1
        return object()

    monkeypatch.setattr(client_module, "create_async_client", _fake_create_async_client)

    first = await client_module.create_server_client()
    second = await client_module.create_server_client()

    assert call_count == 1
    assert first is second


async def test_get_checkpointer_concurrent_calls_run_setup_once(monkeypatch):
    checkpointer._saver = None
    checkpointer._pool = None
    setup_calls = 0

    class _FakePool:
        def __init__(self, *_args, **_kwargs):
            pass

        async def open(self):
            pass

    class _FakeSaver:
        def __init__(self, _pool):
            pass

        async def setup(self):
            nonlocal setup_calls
            setup_calls += 1
            await asyncio.sleep(0.05)

    monkeypatch.setattr(checkpointer, "AsyncConnectionPool", _FakePool)
    monkeypatch.setattr(checkpointer, "AsyncPostgresSaver", _FakeSaver)

    results = await asyncio.gather(*[checkpointer.get_checkpointer() for _ in range(5)])

    assert setup_calls == 1
    assert all(result is results[0] for result in results)


async def test_get_graph_app_concurrent_calls_build_graph_once(monkeypatch):
    graph_module._app = None
    build_calls = 0
    sentinel = object()

    class _FakeGraph:
        def __init__(self, *_args, **_kwargs):
            pass

        def add_node(self, *_args, **_kwargs):
            pass

        def add_edge(self, *_args, **_kwargs):
            pass

        def add_conditional_edges(self, *_args, **_kwargs):
            pass

        def compile(self, **_kwargs):
            nonlocal build_calls
            build_calls += 1
            return sentinel

    async def _fake_get_checkpointer():
        # Duerme mientras se sostiene _app_lock, para forzar que las tareas
        # concurrentes queden bloqueadas esperando el lock en vez de construir
        # cada una su propio grafo.
        await asyncio.sleep(0.05)
        return object()

    monkeypatch.setattr(graph_module, "StateGraph", _FakeGraph)
    monkeypatch.setattr(graph_module, "get_checkpointer", _fake_get_checkpointer)

    results = await asyncio.gather(*[graph_module._get_graph_app() for _ in range(5)])

    assert build_calls == 1
    assert all(result is sentinel for result in results)
