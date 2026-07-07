import pytest

from app.agent import embeddings


@pytest.fixture(autouse=True)
def _reset_embeddings_client():
    embeddings._embeddings_client = None
    yield
    embeddings._embeddings_client = None


class _FakeResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {"data": [{"embedding": [0.1, 0.2, 0.3]}]}


class _FakeAsyncClient:
    instances = 0

    def __init__(self, *args, **kwargs):
        type(self).instances += 1

    async def post(self, *args, **kwargs):
        return _FakeResponse()


@pytest.mark.anyio
async def test_generate_embedding_reuses_the_same_httpx_client_across_calls(monkeypatch):
    # PARTE 2: antes se abria un httpx.AsyncClient (y una conexion TCP+TLS) nuevo en
    # cada llamada. Con el RTT de red medido en el diagnostico (~500ms), eso encarece
    # cada semantic_query/flush de memoria en ~1.5s de puro handshake evitable.
    monkeypatch.setattr(embeddings.httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.instances = 0

    await embeddings.generate_embedding("hola")
    await embeddings.generate_embedding("chau")

    assert _FakeAsyncClient.instances == 1


@pytest.mark.anyio
async def test_generate_embedding_returns_parsed_embedding_vector(monkeypatch):
    monkeypatch.setattr(embeddings.httpx, "AsyncClient", _FakeAsyncClient)

    result = await embeddings.generate_embedding("hola")

    assert result == [0.1, 0.2, 0.3]


@pytest.mark.anyio
async def test_concurrent_calls_still_create_only_one_client(monkeypatch):
    import asyncio

    monkeypatch.setattr(embeddings.httpx, "AsyncClient", _FakeAsyncClient)
    _FakeAsyncClient.instances = 0

    await asyncio.gather(
        embeddings.generate_embedding("a"),
        embeddings.generate_embedding("b"),
        embeddings.generate_embedding("c"),
    )

    assert _FakeAsyncClient.instances == 1
