import json
import logging

from app.logging_config import JSONFormatter


def _format_record(extra: dict) -> dict:
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="test message",
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return json.loads(JSONFormatter().format(record))


def test_formatter_includes_chat_turn_timing_fields():
    # CAMBIO 2: db_ms/agent_ms/total_ms se descartaban en silencio porque no
    # estaban en la tupla de campos permitidos, aunque chat.py ya los pasaba en
    # extra={} para "chat_stream_processed"/"chat_processed".
    payload = _format_record({"event": "chat_stream_processed", "db_ms": 1.2, "agent_ms": 3.4, "total_ms": 5.6})

    assert payload["db_ms"] == 1.2
    assert payload["agent_ms"] == 3.4
    assert payload["total_ms"] == 5.6
    assert payload["event"] == "chat_stream_processed"


def test_formatter_includes_model_selection_fields():
    payload = _format_record(
        {
            "event": "model_selection_rejected",
            "requested_model": "some/model",
            "fallback_model": "google/gemini-2.5-flash",
        }
    )

    assert payload["requested_model"] == "some/model"
    assert payload["fallback_model"] == "google/gemini-2.5-flash"


def test_formatter_includes_remaining_audited_fields():
    payload = _format_record(
        {
            "event": "x",
            "primary_model": "a",
            "model_name": "b",
            "raw_value": "c",
            "failure_count": 2,
        }
    )

    assert payload["primary_model"] == "a"
    assert payload["model_name"] == "b"
    assert payload["raw_value"] == "c"
    assert payload["failure_count"] == 2


def test_formatter_still_anonymizes_user_and_session_ids():
    payload = _format_record({"event": "x", "user_id": "real-user-id", "session_id": "real-session-id"})

    assert payload["user_id"] != "real-user-id"
    assert payload["session_id"] != "real-session-id"
    assert len(payload["user_id"]) == 12
    assert len(payload["session_id"]) == 12


def test_formatter_omits_keys_that_were_never_set_on_the_record():
    payload = _format_record({"event": "x"})

    assert "db_ms" not in payload
    assert "agent_ms" not in payload
    assert "total_ms" not in payload
