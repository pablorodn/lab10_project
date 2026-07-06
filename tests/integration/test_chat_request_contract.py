import asyncio
import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
from starlette.requests import Request

from app.dependencies import get_current_user_id, get_db
from app.main import app


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


def test_chat_rejects_invalid_payload_with_controlled_html_response(
    monkeypatch, patch_auth_middleware, auth_cookie
):
    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id
    monkeypatch.setattr("app.routers.chat.get_session_by_id", lambda *_args, **_kwargs: None)

    client = TestClient(app)
    response = client.post(
        "/api/chat",
        cookies=auth_cookie,
        data={"message": " ", "session_id": ""},
    )
    assert response.status_code == 400
    assert "No pude procesar el mensaje" in response.text
    app.dependency_overrides.clear()


def test_chat_accepts_valid_payload_without_422(monkeypatch, patch_auth_middleware, auth_cookie):
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
            name="Pablo", language="es", timezone="America/Bogota", agent_system_prompt="Sistema"
        )

    async def _fake_tools(_db, _user_id):
        return ["read_file"]

    async def _fake_run_agent(_input):
        from app.agent.graph import AgentOutput

        return AgentOutput(response="ok", tool_calls=[])

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id
    monkeypatch.setattr("app.routers.chat.get_session_by_id", _fake_session)
    monkeypatch.setattr("app.routers.chat.add_message", _fake_add_message)
    monkeypatch.setattr("app.routers.chat.get_profile", _fake_profile)
    monkeypatch.setattr("app.routers.chat.list_enabled_tool_ids", _fake_tools)
    monkeypatch.setattr("app.routers.chat.run_agent", _fake_run_agent)

    client = TestClient(app)
    response = client.post(
        "/api/chat",
        cookies=auth_cookie,
        data={"message": "hola", "session_id": "session-1"},
    )
    assert response.status_code == 200
    assert "ok" in response.text
    app.dependency_overrides.clear()


def test_chat_stream_rejects_invalid_payload_with_sse_error(
    monkeypatch, patch_auth_middleware, auth_cookie
):
    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id
    monkeypatch.setattr("app.routers.chat.get_session_by_id", lambda *_args, **_kwargs: None)

    client = TestClient(app)
    response = client.post(
        "/api/chat/stream",
        cookies=auth_cookie,
        data={"message": " ", "session_id": ""},
    )
    assert response.status_code == 200
    events = _parse_sse_events(response.text)
    assert events[0][0] == "error"
    assert "No pude procesar el mensaje" in events[0][1]["message"]
    app.dependency_overrides.clear()


def test_chat_stream_accepts_valid_payload_and_streams_message_html(
    monkeypatch, patch_auth_middleware, auth_cookie
):
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
            name="Pablo", language="es", timezone="America/Bogota", agent_system_prompt="Sistema"
        )

    async def _fake_tools(_db, _user_id):
        return ["read_file"]

    async def _fake_run_agent(_input):
        from app.agent.graph import AgentOutput

        return AgentOutput(response="ok", tool_calls=[])

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id
    monkeypatch.setattr("app.routers.chat.get_session_by_id", _fake_session)
    monkeypatch.setattr("app.routers.chat.add_message", _fake_add_message)
    monkeypatch.setattr("app.routers.chat.get_profile", _fake_profile)
    monkeypatch.setattr("app.routers.chat.list_enabled_tool_ids", _fake_tools)
    monkeypatch.setattr("app.routers.chat.run_agent", _fake_run_agent)

    client = TestClient(app)
    response = client.post(
        "/api/chat/stream",
        cookies=auth_cookie,
        data={"message": "hola", "session_id": "session-1"},
    )
    assert response.status_code == 200
    events = _parse_sse_events(response.text)
    html_payload = next(data for name, data in events if name == "message_html")
    assert "ok" in html_payload["html"]
    app.dependency_overrides.clear()


def test_chat_returns_404_when_session_not_found(monkeypatch, patch_auth_middleware, auth_cookie):
    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    async def _fake_session_none(_db, _session_id):
        return None

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id
    monkeypatch.setattr("app.routers.chat.get_session_by_id", _fake_session_none)

    client = TestClient(app)
    response = client.post(
        "/api/chat",
        cookies=auth_cookie,
        data={"message": "hola", "session_id": "missing-session"},
    )
    assert response.status_code == 404
    app.dependency_overrides.clear()


def test_chat_returns_403_when_session_belongs_to_another_user(
    monkeypatch, patch_auth_middleware, auth_cookie
):
    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    async def _fake_session_other_user(_db, _session_id):
        return SimpleNamespace(id="session-1", user_id="someone-else", title=None)

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id
    monkeypatch.setattr("app.routers.chat.get_session_by_id", _fake_session_other_user)

    client = TestClient(app)
    response = client.post(
        "/api/chat",
        cookies=auth_cookie,
        data={"message": "hola", "session_id": "session-1"},
    )
    assert response.status_code == 403
    app.dependency_overrides.clear()


def test_chat_stream_emits_sse_error_when_session_not_found(
    monkeypatch, patch_auth_middleware, auth_cookie
):
    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    async def _fake_session_none(_db, _session_id):
        return None

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id
    monkeypatch.setattr("app.routers.chat.get_session_by_id", _fake_session_none)

    client = TestClient(app)
    response = client.post(
        "/api/chat/stream",
        cookies=auth_cookie,
        data={"message": "hola", "session_id": "missing-session"},
    )
    assert response.status_code == 200
    events = _parse_sse_events(response.text)
    assert events == [("error", {"message": "Sesion no encontrada."})]
    app.dependency_overrides.clear()


def test_chat_stream_emits_sse_error_when_session_belongs_to_another_user(
    monkeypatch, patch_auth_middleware, auth_cookie
):
    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    async def _fake_session_other_user(_db, _session_id):
        return SimpleNamespace(id="session-1", user_id="someone-else", title=None)

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id
    monkeypatch.setattr("app.routers.chat.get_session_by_id", _fake_session_other_user)

    client = TestClient(app)
    response = client.post(
        "/api/chat/stream",
        cookies=auth_cookie,
        data={"message": "hola", "session_id": "session-1"},
    )
    assert response.status_code == 200
    events = _parse_sse_events(response.text)
    assert events == [("error", {"message": "Sesion invalida para este usuario."})]
    app.dependency_overrides.clear()


def test_chat_stream_persists_message_when_client_disconnects_mid_generation(
    monkeypatch, patch_auth_middleware, auth_cookie
):
    """Bloque D (H1): si request.is_disconnected() vuelve True mientras el
    agente sigue corriendo, el turno no debe quedar huerfano — el mensaje del
    asistente se persiste igual, aunque no se emita message_html por SSE."""

    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    async def _fake_session(_db, _session_id):
        return SimpleNamespace(id="session-1", user_id="user-1", title="ya tiene titulo")

    persisted_messages: list[dict] = []

    async def _fake_add_message(_db, _session_id, role, content, structured_payload=None):
        persisted_messages.append({"role": role, "content": content})
        return SimpleNamespace(id="msg-1", role=role, content=content)

    async def _fake_profile(_db, _user_id):
        return SimpleNamespace(
            name="Pablo", language="es", timezone="America/Bogota", agent_system_prompt="Sistema"
        )

    async def _fake_tools(_db, _user_id):
        return ["read_file"]

    async def _fake_run_agent(_input):
        from app.agent.graph import AgentOutput

        # Simula trabajo en curso para que el loop de tick alcance a chequear
        # is_disconnected() al menos una vez antes de que agent_task termine.
        await asyncio.sleep(0.05)
        return AgentOutput(response="respuesta generada tras desconexion", tool_calls=[])

    async def _always_disconnected(_self):
        return True

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id
    monkeypatch.setattr("app.routers.chat.get_session_by_id", _fake_session)
    monkeypatch.setattr("app.routers.chat.add_message", _fake_add_message)
    monkeypatch.setattr("app.routers.chat.get_profile", _fake_profile)
    monkeypatch.setattr("app.routers.chat.list_enabled_tool_ids", _fake_tools)
    monkeypatch.setattr("app.routers.chat.run_agent", _fake_run_agent)
    monkeypatch.setattr(Request, "is_disconnected", _always_disconnected)

    client = TestClient(app)
    response = client.post(
        "/api/chat/stream",
        cookies=auth_cookie,
        data={"message": "hola", "session_id": "session-1"},
    )

    assert response.status_code == 200
    events = _parse_sse_events(response.text)
    assert not any(name == "message_html" for name, _ in events)
    assert not any(name == "error" for name, _ in events)

    assert any(
        m["role"] == "assistant" and m["content"] == "respuesta generada tras desconexion"
        for m in persisted_messages
    )
    app.dependency_overrides.clear()


def test_chat_stream_emits_readable_error_when_agent_call_times_out(
    monkeypatch, patch_auth_middleware, auth_cookie
):
    """Bloque A6 (Fase 5): no habia ningun test de timeout en todo el repo.
    Simula el caso representativo de "el modelo (primario y fallback) se
    agoto" haciendo que run_agent propague un TimeoutError real -- exactamente
    lo que pasaria si ainvoke_chat_with_fallback se queda sin fallback (ver
    test_ainvoke_chat_with_fallback_propagates_when_fallback_also_times_out en
    tests/unit/test_model_selection.py). Verifica el catch-all real de
    chat.py:424-435: el usuario recibe un evento SSE "error" legible, no una
    conexion que se corta sin explicacion."""

    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    async def _fake_session(_db, _session_id):
        return SimpleNamespace(id="session-1", user_id="user-1", title=None)

    async def _fake_add_message(_db, _session_id, role, content, structured_payload=None):
        return SimpleNamespace(id="msg-1", role=role, content=content)

    async def _fake_profile(_db, _user_id):
        return SimpleNamespace(
            name="Pablo", language="es", timezone="America/Bogota", agent_system_prompt="Sistema"
        )

    async def _fake_tools(_db, _user_id):
        return ["read_file"]

    async def _fake_run_agent(_input):
        raise TimeoutError("Request timed out after 20.0 seconds")

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id
    monkeypatch.setattr("app.routers.chat.get_session_by_id", _fake_session)
    monkeypatch.setattr("app.routers.chat.add_message", _fake_add_message)
    monkeypatch.setattr("app.routers.chat.get_profile", _fake_profile)
    monkeypatch.setattr("app.routers.chat.list_enabled_tool_ids", _fake_tools)
    monkeypatch.setattr("app.routers.chat.run_agent", _fake_run_agent)

    client = TestClient(app)
    response = client.post(
        "/api/chat/stream",
        cookies=auth_cookie,
        data={"message": "hola", "session_id": "session-1"},
    )

    assert response.status_code == 200
    events = _parse_sse_events(response.text)
    error_events = [data for name, data in events if name == "error"]
    assert error_events
    assert error_events[-1]["message"] == "No pude generar la respuesta. Intenta de nuevo."
    app.dependency_overrides.clear()


def test_chat_non_streaming_returns_readable_error_when_agent_call_times_out(
    monkeypatch, patch_auth_middleware, auth_cookie
):
    """La asimetria que este test documentaba (500 crudo sin mensaje util) se
    corrigio en app/routers/chat.py: la ruta /api/chat ahora envuelve
    run_agent() en un try/except analogo al de /api/chat/stream y devuelve el
    mismo fragmento HTML de error (_error_fragment, con escape de markupsafe
    ya aplicado) que usan los demas errores manejados de este endpoint. Usa
    502 (no 500): la request del cliente era valida, lo que fallo es la
    dependencia upstream (el modelo de chat), asi que no se mezcla con bugs
    no manejados de la app en logs/alertas de monitoreo."""

    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    async def _fake_session(_db, _session_id):
        return SimpleNamespace(id="session-1", user_id="user-1", title=None)

    persisted_messages: list[dict] = []

    async def _fake_add_message(_db, _session_id, role, content, structured_payload=None):
        persisted_messages.append({"role": role, "content": content})
        return SimpleNamespace(id="msg-1", role=role, content=content)

    async def _fake_profile(_db, _user_id):
        return SimpleNamespace(
            name="Pablo", language="es", timezone="America/Bogota", agent_system_prompt="Sistema"
        )

    async def _fake_tools(_db, _user_id):
        return ["read_file"]

    async def _fake_run_agent(_input):
        raise TimeoutError("Request timed out after 20.0 seconds")

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id
    monkeypatch.setattr("app.routers.chat.get_session_by_id", _fake_session)
    monkeypatch.setattr("app.routers.chat.add_message", _fake_add_message)
    monkeypatch.setattr("app.routers.chat.get_profile", _fake_profile)
    monkeypatch.setattr("app.routers.chat.list_enabled_tool_ids", _fake_tools)
    monkeypatch.setattr("app.routers.chat.run_agent", _fake_run_agent)

    client = TestClient(app)
    response = client.post(
        "/api/chat",
        cookies=auth_cookie,
        data={"message": "hola", "session_id": "session-1"},
    )

    assert response.status_code == 502
    assert "No pude generar la respuesta. Intenta de nuevo." in response.text
    # El mensaje del usuario ya se habia persistido antes de invocar al
    # agente (igual que en /api/chat/stream); el turno no queda huerfano.
    assert persisted_messages == [{"role": "user", "content": "hola"}]
    app.dependency_overrides.clear()
