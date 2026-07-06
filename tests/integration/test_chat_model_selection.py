import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.agent.model import FALLBACK_CHAT_MODEL, PRIMARY_CHAT_MODEL
from app.dependencies import get_current_user_id, get_db
from app.main import app
from app.routers.chat import _resolve_chat_model


def _parse_sse_events(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.split("\n\n"):
        block = block.strip("\n")
        if not block:
            continue
        event_name = None
        data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                event_name = line[len("event: ") :]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: ") :])
        if event_name is not None:
            events.append((event_name, data))
    return events


def test_chat_propagates_valid_selected_model_to_agent_input(
    monkeypatch, patch_auth_middleware, auth_cookie
):
    captured: dict[str, object] = {}

    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    async def _fake_session(_db, _session_id):
        return SimpleNamespace(id="session-1", user_id="user-1", title=None)

    async def _fake_add_message(_db, _session_id, role, content, structured_payload=None):
        _ = structured_payload
        return SimpleNamespace(id="msg-1", role=role, content=content)

    async def _fake_profile(_db, _user_id):
        return SimpleNamespace(
            name="Pablo",
            language="es",
            timezone="America/Bogota",
            agent_system_prompt="Sistema",
            default_model=None,
        )

    async def _fake_tools(_db, _user_id):
        return ["read_file"]

    async def _fake_run_agent(agent_input):
        from app.agent.graph import AgentOutput

        captured["chat_model"] = agent_input.chat_model
        return AgentOutput(response="ok", tool_calls=[])

    async def _fake_persist(db, user_id, model_name):
        captured["persisted"] = (user_id, model_name)

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id
    monkeypatch.setattr("app.routers.chat.get_session_by_id", _fake_session)
    monkeypatch.setattr("app.routers.chat.add_message", _fake_add_message)
    monkeypatch.setattr("app.routers.chat.get_profile", _fake_profile)
    monkeypatch.setattr("app.routers.chat.list_enabled_tool_ids", _fake_tools)
    monkeypatch.setattr("app.routers.chat.run_agent", _fake_run_agent)
    monkeypatch.setattr("app.routers.chat._persist_default_model", _fake_persist)

    client = TestClient(app)
    response = client.post(
        "/api/chat",
        cookies=auth_cookie,
        data={"message": "hola", "session_id": "session-1", "chat_model": FALLBACK_CHAT_MODEL},
    )
    assert response.status_code == 200
    assert captured["chat_model"] == FALLBACK_CHAT_MODEL
    app.dependency_overrides.clear()


def test_chat_rejects_unknown_model_and_falls_back_to_primary(
    monkeypatch, patch_auth_middleware, auth_cookie, caplog
):
    captured: dict[str, object] = {}

    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    async def _fake_session(_db, _session_id):
        return SimpleNamespace(id="session-1", user_id="user-1", title=None)

    async def _fake_add_message(_db, _session_id, role, content, structured_payload=None):
        _ = structured_payload
        return SimpleNamespace(id="msg-1", role=role, content=content)

    async def _fake_profile(_db, _user_id):
        return SimpleNamespace(
            name="Pablo",
            language="es",
            timezone="America/Bogota",
            agent_system_prompt="Sistema",
            default_model=None,
        )

    async def _fake_tools(_db, _user_id):
        return ["read_file"]

    async def _fake_run_agent(agent_input):
        from app.agent.graph import AgentOutput

        captured["chat_model"] = agent_input.chat_model
        return AgentOutput(response="ok", tool_calls=[])

    async def _fake_persist(db, user_id, model_name):
        captured["persisted"] = (user_id, model_name)

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id
    monkeypatch.setattr("app.routers.chat.get_session_by_id", _fake_session)
    monkeypatch.setattr("app.routers.chat.add_message", _fake_add_message)
    monkeypatch.setattr("app.routers.chat.get_profile", _fake_profile)
    monkeypatch.setattr("app.routers.chat.list_enabled_tool_ids", _fake_tools)
    monkeypatch.setattr("app.routers.chat.run_agent", _fake_run_agent)
    monkeypatch.setattr("app.routers.chat._persist_default_model", _fake_persist)

    client = TestClient(app)
    with caplog.at_level("WARNING", logger="app.agent.model"):
        response = client.post(
            "/api/chat",
            cookies=auth_cookie,
            data={"message": "hola", "session_id": "session-1", "chat_model": "not-a-real-model"},
        )
    assert response.status_code == 200
    assert captured["chat_model"] == PRIMARY_CHAT_MODEL
    assert any(r.message.startswith("Requested chat model") for r in caplog.records)
    app.dependency_overrides.clear()


def test_chat_stream_propagates_valid_selected_model_to_agent_input(
    monkeypatch, patch_auth_middleware, auth_cookie
):
    captured: dict[str, object] = {}

    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    async def _fake_session(_db, _session_id):
        return SimpleNamespace(id="session-1", user_id="user-1", title=None)

    async def _fake_add_message(_db, _session_id, role, content, structured_payload=None):
        _ = structured_payload
        return SimpleNamespace(id="msg-1", role=role, content=content)

    async def _fake_profile(_db, _user_id):
        return SimpleNamespace(
            name="Pablo",
            language="es",
            timezone="America/Bogota",
            agent_system_prompt="Sistema",
            default_model=None,
        )

    async def _fake_tools(_db, _user_id):
        return ["read_file"]

    async def _fake_run_agent(agent_input):
        from app.agent.graph import AgentOutput

        captured["chat_model"] = agent_input.chat_model
        return AgentOutput(response="ok", tool_calls=[])

    async def _fake_persist(db, user_id, model_name):
        captured["persisted"] = (user_id, model_name)

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id
    monkeypatch.setattr("app.routers.chat.get_session_by_id", _fake_session)
    monkeypatch.setattr("app.routers.chat.add_message", _fake_add_message)
    monkeypatch.setattr("app.routers.chat.get_profile", _fake_profile)
    monkeypatch.setattr("app.routers.chat.list_enabled_tool_ids", _fake_tools)
    monkeypatch.setattr("app.routers.chat.run_agent", _fake_run_agent)
    monkeypatch.setattr("app.routers.chat._persist_default_model", _fake_persist)

    client = TestClient(app)
    response = client.post(
        "/api/chat/stream",
        cookies=auth_cookie,
        data={"message": "hola", "session_id": "session-1", "chat_model": FALLBACK_CHAT_MODEL},
    )
    assert response.status_code == 200
    events = _parse_sse_events(response.text)
    assert any(name == "message_html" for name, _ in events)
    assert captured["chat_model"] == FALLBACK_CHAT_MODEL
    app.dependency_overrides.clear()


def test_chat_stream_rejects_unknown_model_and_falls_back_to_primary(
    monkeypatch, patch_auth_middleware, auth_cookie, caplog
):
    captured: dict[str, object] = {}

    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    async def _fake_session(_db, _session_id):
        return SimpleNamespace(id="session-1", user_id="user-1", title=None)

    async def _fake_add_message(_db, _session_id, role, content, structured_payload=None):
        _ = structured_payload
        return SimpleNamespace(id="msg-1", role=role, content=content)

    async def _fake_profile(_db, _user_id):
        return SimpleNamespace(
            name="Pablo",
            language="es",
            timezone="America/Bogota",
            agent_system_prompt="Sistema",
            default_model=None,
        )

    async def _fake_tools(_db, _user_id):
        return ["read_file"]

    async def _fake_run_agent(agent_input):
        from app.agent.graph import AgentOutput

        captured["chat_model"] = agent_input.chat_model
        return AgentOutput(response="ok", tool_calls=[])

    async def _fake_persist(db, user_id, model_name):
        captured["persisted"] = (user_id, model_name)

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id
    monkeypatch.setattr("app.routers.chat.get_session_by_id", _fake_session)
    monkeypatch.setattr("app.routers.chat.add_message", _fake_add_message)
    monkeypatch.setattr("app.routers.chat.get_profile", _fake_profile)
    monkeypatch.setattr("app.routers.chat.list_enabled_tool_ids", _fake_tools)
    monkeypatch.setattr("app.routers.chat.run_agent", _fake_run_agent)
    monkeypatch.setattr("app.routers.chat._persist_default_model", _fake_persist)

    client = TestClient(app)
    with caplog.at_level("WARNING", logger="app.agent.model"):
        response = client.post(
            "/api/chat/stream",
            cookies=auth_cookie,
            data={"message": "hola", "session_id": "session-1", "chat_model": "not-a-real-model"},
        )
    assert response.status_code == 200
    events = _parse_sse_events(response.text)
    assert any(name == "message_html" for name, _ in events)
    assert captured["chat_model"] == PRIMARY_CHAT_MODEL
    assert any(r.message.startswith("Requested chat model") for r in caplog.records)
    app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_resolve_chat_model_persists_when_it_differs_from_stored_default(monkeypatch):
    persisted_calls: list[tuple[str, str]] = []

    async def _fake_persist(db, user_id, model_name):
        persisted_calls.append((user_id, model_name))

    monkeypatch.setattr("app.routers.chat._persist_default_model", _fake_persist)

    resolved = _resolve_chat_model(FALLBACK_CHAT_MODEL, None, db=object(), user_id="user-1")
    await asyncio.sleep(0)

    assert resolved == FALLBACK_CHAT_MODEL
    assert persisted_calls == [("user-1", FALLBACK_CHAT_MODEL)]


@pytest.mark.anyio
async def test_resolve_chat_model_skips_persistence_when_unchanged(monkeypatch):
    persisted_calls: list[tuple[str, str]] = []

    async def _fake_persist(db, user_id, model_name):
        persisted_calls.append((user_id, model_name))

    monkeypatch.setattr("app.routers.chat._persist_default_model", _fake_persist)

    resolved = _resolve_chat_model(PRIMARY_CHAT_MODEL, PRIMARY_CHAT_MODEL, db=object(), user_id="user-1")
    await asyncio.sleep(0)

    assert resolved == PRIMARY_CHAT_MODEL
    assert persisted_calls == []
