import json

import pytest
from langchain_core.messages import AIMessage

from app.agent.graph import tool_executor_auto_node
from app.tools.catalog import get_tool_definition, get_tool_risk
from app.tools.mcp.example_tool import MCP_EXAMPLE_TOOL_ID, handle_mcp_example_ping


def test_mcp_example_tool_registered_in_catalog():
    definition = get_tool_definition(MCP_EXAMPLE_TOOL_ID)
    assert definition is not None
    assert definition.id == MCP_EXAMPLE_TOOL_ID
    assert get_tool_risk(MCP_EXAMPLE_TOOL_ID) == "low"


@pytest.mark.anyio
async def test_mcp_example_handler_returns_stub_response():
    result = await handle_mcp_example_ping({"message": "hola"}, {})
    assert result == {"pong": True, "echo": "hola", "would_call_server": None}


@pytest.mark.anyio
async def test_mcp_example_tool_executes_via_generic_tool_executor_auto_node(monkeypatch):
    tracking_calls: list[dict[str, object]] = []

    async def _fake_run_with_tracking(**kwargs):
        tracking_calls.append(kwargs)
        return await kwargs["handler"](kwargs["args"])

    monkeypatch.setattr("app.agent.graph.run_with_tracking", _fake_run_with_tracking)

    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "tc-mcp-1",
                        "name": MCP_EXAMPLE_TOOL_ID,
                        "args": {"message": "ping"},
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
                "enabled_tools": [MCP_EXAMPLE_TOOL_ID],
            }
        }
    }

    result = await tool_executor_auto_node(state, config)

    assert len(tracking_calls) == 1
    assert tracking_calls[0]["tool_id"] == MCP_EXAMPLE_TOOL_ID
    # tool_executor_auto_node no incrementa tool_iteration_count (lo hace
    # tool_executor_confirm_node, que siempre corre despues en el grafo real).
    assert "tool_iteration_count" not in result
    assert len(result["messages"]) == 1
    payload = json.loads(result["messages"][0].content)
    assert payload == {"pong": True, "echo": "ping", "would_call_server": None}
