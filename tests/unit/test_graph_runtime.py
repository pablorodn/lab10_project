import json

import pytest
from langchain_core.messages import AIMessage

from app.agent.graph import (
    MAX_TOOL_ITERATIONS,
    parse_pending_confirmation,
    should_continue,
    tool_executor_auto_node,
)

# should_continue(state) con tool_iteration_count == MAX_TOOL_ITERATIONS (limite exacto, 6)
# ya esta cubierto por test_should_continue_routes_to_limit_when_max_iterations_exceeded en
# test_runtime_tracking.py. limit_reached_node() ya esta cubierto (content exacto y sin
# tool_calls) por test_limit_reached_preserves_unexecuted_tool_calls_and_adds_limit_message
# en el mismo archivo. tool_executor_auto_node() para tool conocida-pero-no-habilitada ya esta
# cubierto por test_tool_executor_node_fails_closed_when_no_tools_enabled, y para tool de
# riesgo low ejecutada via run_with_tracking por test_low_tool_execution_inserts_tool_call_record
# (el incremento de tool_iteration_count lo hace tool_executor_confirm_node, no este nodo).
# _build_initial_messages() ya esta cubierto en su totalidad (texto solo, adjuntos solo,
# texto+adjuntos, y el caso vacio) por los 4 tests de test_agent_multimodal.py. Ninguno de
# esos casos se duplica aqui.


def test_should_continue_routes_to_tools_when_under_iteration_limit():
    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[{"id": "tc-1", "name": "get_user_preferences", "args": {}}],
            )
        ],
        "tool_iteration_count": MAX_TOOL_ITERATIONS - 1,
    }

    assert should_continue(state) == "tools"


def test_should_continue_routes_to_end_when_last_message_has_no_tool_calls():
    state = {
        "messages": [AIMessage(content="respuesta final")],
        "tool_iteration_count": 0,
    }

    assert should_continue(state) == "end"


def _full_interrupt_payload(**overrides) -> dict:
    payload = {
        "tool_call_id": "db-tool-id",
        "model_tool_call_id": "model-tool-id",
        "tool_name": "write_file",
        "risk": "high",
        "message": "Confirma accion",
        "args_preview": {"path": "a.txt"},
        "session_id": "session-1",
    }
    payload.update(overrides)
    return payload


def test_parse_pending_confirmation_returns_none_when_no_interrupt_key():
    assert parse_pending_confirmation({}) is None


def test_parse_pending_confirmation_returns_none_when_interrupt_list_empty():
    assert parse_pending_confirmation({"__interrupt__": []}) is None


def test_parse_pending_confirmation_returns_none_when_required_key_missing():
    payload = _full_interrupt_payload()
    del payload["risk"]

    assert parse_pending_confirmation({"__interrupt__": [payload]}) is None


def test_parse_pending_confirmation_maps_all_fields_from_valid_payload():
    payload = _full_interrupt_payload()

    pending = parse_pending_confirmation({"__interrupt__": [payload]})

    assert pending is not None
    assert pending.tool_call_id == "db-tool-id"
    assert pending.model_tool_call_id == "model-tool-id"
    assert pending.tool_name == "write_file"
    assert pending.risk == "high"
    assert pending.message == "Confirma accion"
    assert pending.args_preview == {"path": "a.txt"}
    assert pending.session_id == "session-1"


def test_parse_pending_confirmation_defaults_args_preview_to_empty_dict_when_absent():
    payload = _full_interrupt_payload()
    del payload["args_preview"]

    pending = parse_pending_confirmation({"__interrupt__": [payload]})

    assert pending is not None
    assert pending.args_preview == {}


@pytest.mark.anyio
async def test_tool_executor_node_returns_error_message_for_unknown_tool():
    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[{"id": "tc-unknown-1", "name": "does_not_exist", "args": {}}],
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
                "enabled_tools": ["does_not_exist"],
            }
        }
    }

    result = await tool_executor_auto_node(state, config)

    assert len(result["messages"]) == 1
    assert json.loads(result["messages"][0].content) == {"error": "Unknown tool: does_not_exist"}
    # tool_executor_auto_node no incrementa tool_iteration_count: eso lo hace
    # tool_executor_confirm_node, que siempre corre despues en el grafo real
    # (edge incondicional tools_auto -> tools_confirm) y cierra la ronda.
    assert "tool_iteration_count" not in result
