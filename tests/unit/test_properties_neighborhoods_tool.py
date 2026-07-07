from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.tools.properties.neighborhoods_tool import (
    LIST_NEIGHBORHOODS_TOOL_ID,
    handle_list_neighborhoods,
)
from app.tools.schemas import ListNeighborhoodsArgs

SAMPLE_NEIGHBORHOOD_RESULT = {
    "neighborhood": "El Ingenio",
    "property_count": 4,
    "min_price_cop": 1800000,
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
        "app.tools.properties.neighborhoods_tool.get_settings",
        lambda: SimpleNamespace(is_properties_db_configured=configured),
    )


@pytest.mark.anyio
async def test_not_configured_returns_error_dict_without_raising(monkeypatch):
    _patch_configured(monkeypatch, False)

    result = await handle_list_neighborhoods({}, {})

    assert result == {
        "error": "not_configured",
        "message": "La búsqueda de propiedades no está configurada actualmente.",
    }


@pytest.mark.anyio
async def test_successful_search_maps_friendly_args_to_rpc_params(monkeypatch):
    _patch_configured(monkeypatch, True)
    fake_client = _FakeSupabaseClient([SAMPLE_NEIGHBORHOOD_RESULT])
    monkeypatch.setattr(
        "app.tools.properties.neighborhoods_tool.create_properties_client",
        _client_factory(fake_client),
    )

    args = ListNeighborhoodsArgs(
        operation_type="arriendo",
        property_type="apartamento",
        min_bedrooms=2,
        min_bathrooms=1,
        min_parking=1,
        min_price_cop=1000000,
        max_price_cop=3000000,
        min_area_m2=50,
        stratum=3,
        limit=10,
    ).model_dump()

    result = await handle_list_neighborhoods(args, {})

    assert len(fake_client.rpc_calls) == 1
    fn_name, params = fake_client.rpc_calls[0]
    assert fn_name == "neighborhoods_by_filters"
    assert params == {
        "p_operation_type": "arriendo",
        "p_property_type": "apartamento",
        "p_min_bedrooms": 2,
        "p_min_bathrooms": 1,
        "p_min_parking": 1,
        "p_min_price_cop": 1000000,
        "p_max_price_cop": 3000000,
        "p_min_area_m2": 50,
        "p_stratum": 3,
        "p_limit": 10,
    }
    assert result["count"] == 1
    assert result["results"] == [SAMPLE_NEIGHBORHOOD_RESULT]
    assert "El Ingenio" in result["formatted_markdown"]
    assert "4 opciones" in result["formatted_markdown"]
    assert "$1.800.000 COP" in result["formatted_markdown"]


@pytest.mark.anyio
async def test_zero_results_returns_friendly_message_and_empty_markdown(monkeypatch):
    _patch_configured(monkeypatch, True)
    fake_client = _FakeSupabaseClient([])
    monkeypatch.setattr(
        "app.tools.properties.neighborhoods_tool.create_properties_client",
        _client_factory(fake_client),
    )

    result = await handle_list_neighborhoods({}, {})

    assert result == {
        "results": [],
        "count": 0,
        "formatted_markdown": "",
        "message": "No encontré barrios que coincidan con esos criterios.",
    }


@pytest.mark.anyio
async def test_rpc_exception_is_caught_and_returns_error_dict_without_raising(monkeypatch):
    _patch_configured(monkeypatch, True)
    monkeypatch.setattr(
        "app.tools.properties.neighborhoods_tool.create_properties_client",
        _client_factory(_FailingRPCClient()),
    )

    result = await handle_list_neighborhoods({}, {})

    assert result == {
        "error": "search_failed",
        "message": "No pude completar la búsqueda de barrios en este momento.",
    }


def test_neighborhoods_tool_id_matches_catalog_id():
    assert LIST_NEIGHBORHOODS_TOOL_ID == "list_neighborhoods"


def test_limit_below_minimum_raises_validation_error():
    with pytest.raises(ValidationError):
        ListNeighborhoodsArgs(limit=0)


def test_limit_above_maximum_raises_validation_error():
    with pytest.raises(ValidationError):
        ListNeighborhoodsArgs(limit=51)


def test_limit_within_range_is_accepted():
    assert ListNeighborhoodsArgs(limit=50).limit == 50
    assert ListNeighborhoodsArgs(limit=1).limit == 1


def test_singular_option_count():
    """Verifica que la salida usa singular 'opción' cuando count=1."""
    from app.tools.properties.neighborhoods_tool import _build_neighborhood_line

    row = {"neighborhood": "Test Barrio", "property_count": 1, "min_price_cop": 1000000}
    result = _build_neighborhood_line(row)
    assert "1 opción" in result


def test_plural_option_count():
    """Verifica que la salida usa plural 'opciones' cuando count>1."""
    from app.tools.properties.neighborhoods_tool import _build_neighborhood_line

    row = {"neighborhood": "Test Barrio", "property_count": 5, "min_price_cop": 1000000}
    result = _build_neighborhood_line(row)
    assert "5 opciones" in result
