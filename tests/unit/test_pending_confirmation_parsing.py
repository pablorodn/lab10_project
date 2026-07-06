from app.agent.graph import parse_pending_confirmation


def test_parse_pending_confirmation_from_interrupt_payload():
    final_state = {
        "__interrupt__": [
            {
                "tool_call_id": "db-tool-id",
                "model_tool_call_id": "model-tool-id",
                "tool_name": "write_file",
                "risk": "high",
                "message": "Confirma acción",
                "args_preview": {"title": "Bug"},
                "session_id": "session-1",
            }
        ]
    }
    pending = parse_pending_confirmation(final_state)
    assert pending is not None
    assert pending.tool_call_id == "db-tool-id"
    assert pending.model_tool_call_id == "model-tool-id"
