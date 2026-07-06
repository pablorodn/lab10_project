from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.tools.properties.search_tool import (
    SEARCH_PROPERTIES_TOOL_ID,
    handle_search_properties,
)
from app.tools.schemas import SearchPropertiesArgs

SAMPLE_ROW = {
    "id": "11111111-1111-1111-1111-111111111111",
    "title": "Apto en Pance",
    "operation_type": "venta",
    "property_type": "apartamento",
    "price_cop": 350000000,
    "area_m2": 85,
    "bedrooms": 3,
    "bathrooms": 2,
    "parking_spots": 1,
    "neighborhood": "Pance",
    "comuna": "Comuna 17",
    "stratum": 5,
    "listing_url": "https://example.com/listing/1",
    "similarity": 0.87,
}


class _FakeRPCBuilder:
    def __init__(self, response_data):
        self._response_data = response_data

    async def execute(self):
        return SimpleNamespace(data=self._response_data)


class _FakeSupabaseClient:
    def __init__(self, response_data):
        self._response_data = response_data
        self.rpc_calls: list[tuple[str, dict]] = []

    def rpc(self, fn_name, params):
        self.rpc_calls.append((fn_name, params))
        return _FakeRPCBuilder(self._response_data)


class _FailingRPCBuilder:
    async def execute(self):
        raise RuntimeError("rpc unreachable")


class _FailingRPCClient:
    def rpc(self, fn_name, params):
        return _FailingRPCBuilder()


def _client_factory(client):
    async def _create():
        return client

    return _create


def _patch_configured(monkeypatch, configured: bool):
    monkeypatch.setattr(
        "app.tools.properties.search_tool.get_settings",
        lambda: SimpleNamespace(is_properties_db_configured=configured),
    )


@pytest.mark.anyio
async def test_not_configured_returns_error_dict_without_raising(monkeypatch):
    _patch_configured(monkeypatch, False)

    result = await handle_search_properties({}, {})

    assert result == {
        "error": "not_configured",
        "message": "La búsqueda de propiedades no está configurada actualmente.",
    }


@pytest.mark.anyio
async def test_successful_search_maps_friendly_args_to_rpc_params(monkeypatch):
    _patch_configured(monkeypatch, True)
    fake_client = _FakeSupabaseClient([SAMPLE_ROW])
    monkeypatch.setattr(
        "app.tools.properties.search_tool.create_properties_client",
        _client_factory(fake_client),
    )

    async def _fail_if_called(_text):
        raise AssertionError("generate_embedding no debería llamarse sin semantic_query")

    monkeypatch.setattr(
        "app.tools.properties.search_tool.generate_embedding", _fail_if_called
    )

    args = SearchPropertiesArgs(
        operation_type="venta",
        property_type="apartamento",
        neighborhood="pance",
        comuna="Comuna 17",
        min_bedrooms=2,
        min_bathrooms=1,
        min_parking=1,
        min_price_cop=100_000_000,
        max_price_cop=500_000_000,
        min_area_m2=50,
        stratum=5,
        limit=5,
    ).model_dump()

    result = await handle_search_properties(args, {})

    assert len(fake_client.rpc_calls) == 1
    fn_name, params = fake_client.rpc_calls[0]
    assert fn_name == "match_properties"
    assert params == {
        "query_embedding": None,
        "p_operation_type": "venta",
        "p_property_type": "apartamento",
        "p_neighborhood": "pance",
        "p_comuna": "Comuna 17",
        "p_min_bedrooms": 2,
        "p_min_bathrooms": 1,
        "p_min_parking": 1,
        "p_min_price_cop": 100_000_000,
        "p_max_price_cop": 500_000_000,
        "p_min_area_m2": 50,
        "p_stratum": 5,
        "match_count": 5,
    }
    assert result["count"] == 1
    assert result["results"] == [SAMPLE_ROW]
    assert "[Ver publicación](https://example.com/listing/1)" in result["formatted_markdown"]
    assert "<a" not in result["formatted_markdown"]


@pytest.mark.anyio
async def test_semantic_query_triggers_embedding_and_passes_as_query_embedding(monkeypatch):
    _patch_configured(monkeypatch, True)
    fake_client = _FakeSupabaseClient([])
    monkeypatch.setattr(
        "app.tools.properties.search_tool.create_properties_client",
        _client_factory(fake_client),
    )

    captured_texts: list[str] = []

    async def _fake_generate_embedding(text):
        captured_texts.append(text)
        return [0.1, 0.2, 0.3]

    monkeypatch.setattr(
        "app.tools.properties.search_tool.generate_embedding", _fake_generate_embedding
    )

    await handle_search_properties({"semantic_query": "  con balcón y luz  "}, {})

    assert captured_texts == ["con balcón y luz"]
    assert fake_client.rpc_calls[0][1]["query_embedding"] == [0.1, 0.2, 0.3]


@pytest.mark.anyio
async def test_blank_semantic_query_does_not_call_generate_embedding(monkeypatch):
    _patch_configured(monkeypatch, True)
    fake_client = _FakeSupabaseClient([])
    monkeypatch.setattr(
        "app.tools.properties.search_tool.create_properties_client",
        _client_factory(fake_client),
    )

    async def _fail_if_called(_text):
        raise AssertionError("generate_embedding no debería llamarse")

    monkeypatch.setattr(
        "app.tools.properties.search_tool.generate_embedding", _fail_if_called
    )

    result = await handle_search_properties({"semantic_query": "   "}, {})

    assert fake_client.rpc_calls[0][1]["query_embedding"] is None
    assert result["count"] == 0


@pytest.mark.anyio
async def test_zero_results_returns_friendly_message_and_empty_markdown(monkeypatch):
    _patch_configured(monkeypatch, True)
    fake_client = _FakeSupabaseClient([])
    monkeypatch.setattr(
        "app.tools.properties.search_tool.create_properties_client",
        _client_factory(fake_client),
    )

    result = await handle_search_properties({}, {})

    assert result == {
        "results": [],
        "count": 0,
        "formatted_markdown": "",
        "message": "No encontré propiedades que coincidan con esos criterios. "
        "Podrías intentar con filtros más amplios.",
    }


@pytest.mark.anyio
async def test_rpc_exception_is_caught_and_returns_error_dict_without_raising(monkeypatch):
    _patch_configured(monkeypatch, True)
    monkeypatch.setattr(
        "app.tools.properties.search_tool.create_properties_client",
        _client_factory(_FailingRPCClient()),
    )

    result = await handle_search_properties({}, {})

    assert result == {
        "error": "search_failed",
        "message": "No pude completar la búsqueda de propiedades en este momento.",
    }


@pytest.mark.anyio
async def test_generate_embedding_exception_is_caught_and_returns_error_dict(monkeypatch):
    _patch_configured(monkeypatch, True)
    fake_client = _FakeSupabaseClient([SAMPLE_ROW])
    monkeypatch.setattr(
        "app.tools.properties.search_tool.create_properties_client",
        _client_factory(fake_client),
    )

    async def _failing_generate_embedding(_text):
        raise RuntimeError("openrouter down")

    monkeypatch.setattr(
        "app.tools.properties.search_tool.generate_embedding", _failing_generate_embedding
    )

    result = await handle_search_properties({"semantic_query": "algo"}, {})

    assert result == {
        "error": "search_failed",
        "message": "No pude completar la búsqueda de propiedades en este momento.",
    }


def test_search_properties_tool_id_matches_catalog_id():
    assert SEARCH_PROPERTIES_TOOL_ID == "search_properties"


def test_limit_below_minimum_raises_validation_error():
    with pytest.raises(ValidationError):
        SearchPropertiesArgs(limit=0)


def test_limit_above_maximum_raises_validation_error():
    with pytest.raises(ValidationError):
        SearchPropertiesArgs(limit=16)


def test_limit_within_range_is_accepted():
    assert SearchPropertiesArgs(limit=15).limit == 15
    assert SearchPropertiesArgs(limit=1).limit == 1
