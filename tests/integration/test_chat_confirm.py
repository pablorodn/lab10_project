from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.dependencies import get_current_user_id, get_db
from app.main import app


def test_chat_confirm_returns_403_when_tool_call_belongs_to_another_user(
    monkeypatch, patch_auth_middleware, auth_cookie
):
    """Bloque A1 (Fase 5): /api/chat/confirm no tenia ningun test hasta ahora.
    El chequeo de ownership (chat.py:488-489) compara el user_id de la sesion
    dueña del tool_call pendiente contra el usuario autenticado -- si alguien
    lo rompe, esto es lo unico que lo detecta."""

    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    async def _fake_pending_tool_call(_db, tool_call_id):
        return SimpleNamespace(id=tool_call_id, session_id="session-owned-by-other")

    async def _fake_session_other_user(_db, _session_id):
        return SimpleNamespace(id="session-owned-by-other", user_id="someone-else", title=None)

    run_agent_calls: list[object] = []

    async def _fake_run_agent(agent_input):
        run_agent_calls.append(agent_input)
        raise AssertionError("run_agent no debe invocarse si el tool_call no pertenece al usuario")

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id
    monkeypatch.setattr("app.routers.chat.get_pending_tool_call", _fake_pending_tool_call)
    monkeypatch.setattr("app.routers.chat.get_session_by_id", _fake_session_other_user)
    monkeypatch.setattr("app.routers.chat.run_agent", _fake_run_agent)

    client = TestClient(app)
    response = client.post(
        "/api/chat/confirm",
        cookies=auth_cookie,
        data={"tool_call_id": "tc-1", "action": "approve"},
    )

    assert response.status_code == 403
    assert run_agent_calls == []
    app.dependency_overrides.clear()


def test_chat_confirm_returns_404_when_tool_call_not_pending_or_missing(
    monkeypatch, patch_auth_middleware, auth_cookie
):
    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    async def _fake_pending_tool_call_none(_db, _tool_call_id):
        return None

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id
    monkeypatch.setattr("app.routers.chat.get_pending_tool_call", _fake_pending_tool_call_none)

    client = TestClient(app)
    response = client.post(
        "/api/chat/confirm",
        cookies=auth_cookie,
        data={"tool_call_id": "does-not-exist", "action": "approve"},
    )

    assert response.status_code == 404
    app.dependency_overrides.clear()


def test_chat_confirm_approve_by_owner_resumes_agent_and_renders_message(
    monkeypatch, patch_auth_middleware, auth_cookie
):
    """Caso feliz: dueño correcto, action=approve. Verifica el contrato real
    (resume_decision propagado + contenido del HTML devuelto), no solo 200."""

    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    async def _fake_pending_tool_call(_db, tool_call_id):
        return SimpleNamespace(id=tool_call_id, session_id="session-1")

    async def _fake_session_owner(_db, _session_id):
        return SimpleNamespace(id="session-1", user_id="user-1", title="ya tiene titulo")

    async def _fake_profile(_db, _user_id):
        return SimpleNamespace(
            name="Pablo", language="es", timezone="America/Bogota", agent_system_prompt="Sistema"
        )

    async def _fake_tools(_db, _user_id):
        return ["write_file"]

    captured_input = {}

    async def _fake_run_agent(agent_input):
        from app.agent.graph import AgentOutput

        captured_input["resume_decision"] = agent_input.resume_decision
        captured_input["session_id"] = agent_input.session_id
        captured_input["enabled_tools"] = agent_input.enabled_tools
        return AgentOutput(response="Archivo creado correctamente.", tool_calls=["write_file"])

    persisted_messages = []

    async def _fake_add_message(_db, session_id, role, content, structured_payload=None):
        persisted_messages.append({"session_id": session_id, "role": role, "content": content})
        return SimpleNamespace(id="msg-2", role=role, content=content)

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id
    monkeypatch.setattr("app.routers.chat.get_pending_tool_call", _fake_pending_tool_call)
    monkeypatch.setattr("app.routers.chat.get_session_by_id", _fake_session_owner)
    monkeypatch.setattr("app.routers.chat.get_profile", _fake_profile)
    monkeypatch.setattr("app.routers.chat.list_enabled_tool_ids", _fake_tools)
    monkeypatch.setattr("app.routers.chat.run_agent", _fake_run_agent)
    monkeypatch.setattr("app.routers.chat.add_message", _fake_add_message)

    client = TestClient(app)
    response = client.post(
        "/api/chat/confirm",
        cookies=auth_cookie,
        data={"tool_call_id": "tc-1", "action": "approve"},
    )

    assert response.status_code == 200
    assert "Archivo creado correctamente." in response.text
    # El endpoint debe pasar la accion del usuario tal cual como resume_decision,
    # no hardcodear "approve" sin importar lo que llego en el form.
    assert captured_input["resume_decision"] == "approve"
    assert captured_input["session_id"] == "session-1"
    assert persisted_messages == [
        {"session_id": "session-1", "role": "assistant", "content": "Archivo creado correctamente."}
    ]
    app.dependency_overrides.clear()


def test_chat_confirm_rejects_invalid_action_value(monkeypatch, patch_auth_middleware, auth_cookie):
    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id

    client = TestClient(app)
    response = client.post(
        "/api/chat/confirm",
        cookies=auth_cookie,
        data={"tool_call_id": "tc-1", "action": "delete"},
    )

    assert response.status_code == 400
    app.dependency_overrides.clear()
