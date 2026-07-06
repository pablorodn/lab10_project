import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

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


def _install_common_fakes(monkeypatch, captured: dict):
    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    async def _fake_session(_db, _session_id):
        return SimpleNamespace(id="session-1", user_id="user-1", title=None)

    async def _fake_add_message(_db, _session_id, role, content, structured_payload=None):
        captured.setdefault("messages", []).append(
            {"role": role, "content": content, "structured_payload": structured_payload}
        )
        return SimpleNamespace(id=f"msg-{len(captured['messages'])}", role=role, content=content)

    async def _fake_profile(_db, _user_id):
        return SimpleNamespace(
            name="Pablo", language="es", timezone="America/Bogota", agent_system_prompt="Sistema"
        )

    async def _fake_tools(_db, _user_id):
        return ["read_file"]

    async def _fake_run_agent(agent_input):
        from app.agent.graph import AgentOutput

        captured["agent_input"] = agent_input
        return AgentOutput(response="ok", tool_calls=[])

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id
    monkeypatch.setattr("app.routers.chat.get_session_by_id", _fake_session)
    monkeypatch.setattr("app.routers.chat.add_message", _fake_add_message)
    monkeypatch.setattr("app.routers.chat.get_profile", _fake_profile)
    monkeypatch.setattr("app.routers.chat.list_enabled_tool_ids", _fake_tools)
    monkeypatch.setattr("app.routers.chat.run_agent", _fake_run_agent)


def test_chat_with_image_attachment_builds_multimodal_message_and_note(
    monkeypatch, patch_auth_middleware, auth_cookie
):
    captured: dict = {}
    _install_common_fakes(monkeypatch, captured)

    client = TestClient(app)
    response = client.post(
        "/api/chat",
        cookies=auth_cookie,
        data={"message": "mira esta foto", "session_id": "session-1"},
        files=[("attachments", ("photo.png", b"\x89PNG\r\n\x1a\n", "image/png"))],
    )

    assert response.status_code == 200
    user_message = captured["messages"][0]
    assert user_message["role"] == "user"
    assert user_message["structured_payload"] == {
        "type": "attachment_note",
        "count": 1,
        "kinds": ["image"],
    }

    agent_input = captured["agent_input"]
    assert agent_input.message == "mira esta foto"
    assert agent_input.attachment_blocks is not None
    assert len(agent_input.attachment_blocks) == 1
    assert agent_input.attachment_blocks[0]["type"] == "image"
    assert agent_input.attachment_blocks[0]["mime_type"] == "image/png"
    app.dependency_overrides.clear()


def test_chat_allows_attachment_only_message_with_empty_text(
    monkeypatch, patch_auth_middleware, auth_cookie
):
    captured: dict = {}
    _install_common_fakes(monkeypatch, captured)

    client = TestClient(app)
    response = client.post(
        "/api/chat",
        cookies=auth_cookie,
        data={"message": "", "session_id": "session-1"},
        files=[("attachments", ("photo.png", b"\x89PNG\r\n\x1a\n", "image/png"))],
    )

    assert response.status_code == 200
    user_message = captured["messages"][0]
    assert user_message["content"] == ""
    assert user_message["structured_payload"]["kinds"] == ["image"]
    app.dependency_overrides.clear()


def test_chat_rejects_oversized_image_without_persisting_message(
    monkeypatch, patch_auth_middleware, auth_cookie
):
    captured: dict = {}
    _install_common_fakes(monkeypatch, captured)

    client = TestClient(app)
    oversized = b"x" * (5 * 1024 * 1024 + 1)
    response = client.post(
        "/api/chat",
        cookies=auth_cookie,
        data={"message": "hola", "session_id": "session-1"},
        files=[("attachments", ("big.png", oversized, "image/png"))],
    )

    assert response.status_code == 400
    assert "5 MB" in response.text
    assert "messages" not in captured
    app.dependency_overrides.clear()


def test_chat_rejects_disallowed_mime_type(monkeypatch, patch_auth_middleware, auth_cookie):
    captured: dict = {}
    _install_common_fakes(monkeypatch, captured)

    client = TestClient(app)
    response = client.post(
        "/api/chat",
        cookies=auth_cookie,
        data={"message": "hola", "session_id": "session-1"},
        files=[("attachments", ("archive.zip", b"data", "application/zip"))],
    )

    assert response.status_code == 400
    assert "no permitido" in response.text
    assert "messages" not in captured
    app.dependency_overrides.clear()


def test_chat_error_fragment_escapes_malicious_attachment_filename(
    monkeypatch, patch_auth_middleware, auth_cookie
):
    """Regresion de seguridad (Fase 4, hallazgo incidental): _error_fragment en
    app/routers/chat.py interpolaba el mensaje de error sin escapar HTML. Como
    ese mensaje incluye file.filename tal cual lo eligio el usuario (ver
    AttachmentValidationError en app/services/attachments.py), subir un
    archivo con un nombre malicioso por la ruta sin streaming (POST /api/chat)
    reflejaba ese HTML/JS crudo en la respuesta: XSS reflejada real.
    """
    captured: dict = {}
    _install_common_fakes(monkeypatch, captured)

    malicious_filename = "<script>alert(1)</script>.zip"

    client = TestClient(app)
    response = client.post(
        "/api/chat",
        cookies=auth_cookie,
        data={"message": "hola", "session_id": "session-1"},
        files=[("attachments", (malicious_filename, b"data", "application/zip"))],
    )

    assert response.status_code == 400
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in response.text
    assert "messages" not in captured
    app.dependency_overrides.clear()


def test_chat_rejects_more_than_three_attachments(monkeypatch, patch_auth_middleware, auth_cookie):
    captured: dict = {}
    _install_common_fakes(monkeypatch, captured)

    client = TestClient(app)
    files = [("attachments", (f"{i}.png", b"data", "image/png")) for i in range(4)]
    response = client.post(
        "/api/chat",
        cookies=auth_cookie,
        data={"message": "hola", "session_id": "session-1"},
        files=files,
    )

    assert response.status_code == 400
    assert "Máximo 3" in response.text
    assert "messages" not in captured
    app.dependency_overrides.clear()


def test_chat_stream_with_image_attachment_builds_multimodal_message_and_note(
    monkeypatch, patch_auth_middleware, auth_cookie
):
    captured: dict = {}
    _install_common_fakes(monkeypatch, captured)

    client = TestClient(app)
    response = client.post(
        "/api/chat/stream",
        cookies=auth_cookie,
        data={"message": "mira esta foto", "session_id": "session-1"},
        files=[("attachments", ("photo.png", b"\x89PNG\r\n\x1a\n", "image/png"))],
    )

    assert response.status_code == 200
    events = _parse_sse_events(response.text)
    assert any(name == "message_html" for name, _ in events)

    user_message = captured["messages"][0]
    assert user_message["role"] == "user"
    assert user_message["structured_payload"] == {
        "type": "attachment_note",
        "count": 1,
        "kinds": ["image"],
    }

    agent_input = captured["agent_input"]
    assert agent_input.message == "mira esta foto"
    assert agent_input.attachment_blocks is not None
    assert len(agent_input.attachment_blocks) == 1
    assert agent_input.attachment_blocks[0]["type"] == "image"
    assert agent_input.attachment_blocks[0]["mime_type"] == "image/png"
    app.dependency_overrides.clear()


def test_chat_stream_allows_attachment_only_message_with_empty_text(
    monkeypatch, patch_auth_middleware, auth_cookie
):
    captured: dict = {}
    _install_common_fakes(monkeypatch, captured)

    client = TestClient(app)
    response = client.post(
        "/api/chat/stream",
        cookies=auth_cookie,
        data={"message": "", "session_id": "session-1"},
        files=[("attachments", ("photo.png", b"\x89PNG\r\n\x1a\n", "image/png"))],
    )

    assert response.status_code == 200
    user_message = captured["messages"][0]
    assert user_message["content"] == ""
    assert user_message["structured_payload"]["kinds"] == ["image"]
    app.dependency_overrides.clear()


def test_chat_stream_rejects_oversized_image_without_persisting_message(
    monkeypatch, patch_auth_middleware, auth_cookie
):
    captured: dict = {}
    _install_common_fakes(monkeypatch, captured)

    client = TestClient(app)
    oversized = b"x" * (5 * 1024 * 1024 + 1)
    response = client.post(
        "/api/chat/stream",
        cookies=auth_cookie,
        data={"message": "hola", "session_id": "session-1"},
        files=[("attachments", ("big.png", oversized, "image/png"))],
    )

    assert response.status_code == 200
    events = _parse_sse_events(response.text)
    assert events[0][0] == "error"
    assert "5 MB" in events[0][1]["message"]
    assert "messages" not in captured
    app.dependency_overrides.clear()


def test_chat_stream_rejects_disallowed_mime_type(monkeypatch, patch_auth_middleware, auth_cookie):
    captured: dict = {}
    _install_common_fakes(monkeypatch, captured)

    client = TestClient(app)
    response = client.post(
        "/api/chat/stream",
        cookies=auth_cookie,
        data={"message": "hola", "session_id": "session-1"},
        files=[("attachments", ("archive.zip", b"data", "application/zip"))],
    )

    assert response.status_code == 200
    events = _parse_sse_events(response.text)
    assert events[0][0] == "error"
    assert "no permitido" in events[0][1]["message"]
    assert "messages" not in captured
    app.dependency_overrides.clear()


def test_chat_stream_rejects_more_than_three_attachments(
    monkeypatch, patch_auth_middleware, auth_cookie
):
    captured: dict = {}
    _install_common_fakes(monkeypatch, captured)

    client = TestClient(app)
    files = [("attachments", (f"{i}.png", b"data", "image/png")) for i in range(4)]
    response = client.post(
        "/api/chat/stream",
        cookies=auth_cookie,
        data={"message": "hola", "session_id": "session-1"},
        files=files,
    )

    assert response.status_code == 200
    events = _parse_sse_events(response.text)
    assert events[0][0] == "error"
    assert "Máximo 3" in events[0][1]["message"]
    assert "messages" not in captured
    app.dependency_overrides.clear()
