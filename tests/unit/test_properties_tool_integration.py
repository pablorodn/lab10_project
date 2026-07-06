import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from app.agent.graph import tool_executor_auto_node
from app.tools.adapters import TOOL_HANDLERS
from app.tools.catalog import get_tool_definition, get_tool_risk
from app.tools.properties.search_tool import SEARCH_PROPERTIES_TOOL_ID

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


def test_search_properties_registered_in_catalog_and_adapters():
    definition = get_tool_definition(SEARCH_PROPERTIES_TOOL_ID)
    assert definition is not None
    assert definition.id == SEARCH_PROPERTIES_TOOL_ID
    assert get_tool_risk(SEARCH_PROPERTIES_TOOL_ID) == "low"
    assert SEARCH_PROPERTIES_TOOL_ID in TOOL_HANDLERS


@pytest.mark.anyio
async def test_search_properties_executes_via_generic_tool_executor_auto_node(monkeypatch):
    tracking_calls: list[dict[str, object]] = []

    async def _fake_run_with_tracking(**kwargs):
        tracking_calls.append(kwargs)
        return await kwargs["handler"](kwargs["args"])

    monkeypatch.setattr("app.agent.graph.run_with_tracking", _fake_run_with_tracking)
    monkeypatch.setattr(
        "app.tools.properties.search_tool.get_settings",
        lambda: SimpleNamespace(is_properties_db_configured=True),
    )

    class _FakeRPCBuilder:
        async def execute(self):
            return SimpleNamespace(data=[SAMPLE_ROW])

    class _FakeSupabaseClient:
        def rpc(self, fn_name, params):
            self.last_call = (fn_name, params)
            return _FakeRPCBuilder()

    fake_client = _FakeSupabaseClient()

    async def _fake_create_properties_client():
        return fake_client

    monkeypatch.setattr(
        "app.tools.properties.search_tool.create_properties_client",
        _fake_create_properties_client,
    )

    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "tc-props-1",
                        "name": SEARCH_PROPERTIES_TOOL_ID,
                        "args": {"neighborhood": "pance", "limit": 5},
                    }
                ],
            )
        ],
        "session_id": "session-1",
        "tool_iteration_count": 0,
    }
    config = {
        "configurable": {
            "tool_ctx": {
                "db": object(),
                "user_id": "user-1",
                "session_id": "session-1",
                "enabled_tools": [SEARCH_PROPERTIES_TOOL_ID],
            }
        }
    }

    result = await tool_executor_auto_node(state, config)

    assert len(tracking_calls) == 1
    assert tracking_calls[0]["tool_id"] == SEARCH_PROPERTIES_TOOL_ID
    assert "tool_iteration_count" not in result
    assert len(result["messages"]) == 1

    payload = json.loads(result["messages"][0].content)
    assert payload["count"] == 1
    assert payload["results"] == [SAMPLE_ROW]
    assert "[Ver publicación](https://example.com/listing/1)" in payload["formatted_markdown"]
    assert "<a" not in payload["formatted_markdown"]

    fn_name, params = fake_client.last_call
    assert fn_name == "match_properties"
    assert params["p_neighborhood"] == "pance"
    assert params["match_count"] == 5
