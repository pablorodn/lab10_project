from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.dependencies import get_current_user_id, get_db
from app.main import app


def _install_common_fakes(monkeypatch, *, session_user_id="user-1", session_id="session-1"):
    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    async def _fake_session(_db, sid):
        return SimpleNamespace(id=sid, user_id=session_user_id, title=None)

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id
    monkeypatch.setattr("app.routers.sessions.get_session_by_id", _fake_session)


def test_archive_unknown_session_returns_404(monkeypatch, patch_auth_middleware, auth_cookie):
    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    async def _fake_session(_db, _sid):
        return None

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id
    monkeypatch.setattr("app.routers.sessions.get_session_by_id", _fake_session)

    client = TestClient(app)
    response = client.post("/api/sessions/session-1/archive", cookies=auth_cookie)
    assert response.status_code == 404
    app.dependency_overrides.clear()


def test_delete_session_owned_by_another_user_returns_403(monkeypatch, patch_auth_middleware, auth_cookie):
    _install_common_fakes(monkeypatch, session_user_id="someone-else")

    client = TestClient(app)
    response = client.post("/api/sessions/session-1/delete", cookies=auth_cookie)
    assert response.status_code == 403
    app.dependency_overrides.clear()


def test_clear_unknown_session_returns_404(monkeypatch, patch_auth_middleware, auth_cookie):
    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    async def _fake_session(_db, _sid):
        return None

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id
    monkeypatch.setattr("app.routers.sessions.get_session_by_id", _fake_session)

    client = TestClient(app)
    response = client.post("/api/sessions/session-1/clear", cookies=auth_cookie)
    assert response.status_code == 404
    app.dependency_overrides.clear()


def test_clear_session_owned_by_another_user_returns_403(monkeypatch, patch_auth_middleware, auth_cookie):
    """Bloque C2 (Fase 5): /api/sessions/{id}/clear no tenia ningun test."""
    _install_common_fakes(monkeypatch, session_user_id="someone-else")

    cleared_calls: list[str] = []

    async def _fake_clear_session_messages(_db, session_id):
        cleared_calls.append(session_id)

    monkeypatch.setattr("app.routers.sessions.clear_session_messages", _fake_clear_session_messages)

    client = TestClient(app)
    response = client.post("/api/sessions/session-1/clear", cookies=auth_cookie)
    assert response.status_code == 403
    assert cleared_calls == []
    app.dependency_overrides.clear()


def test_clear_session_owned_by_user_calls_clear_session_messages_with_correct_id(
    monkeypatch, patch_auth_middleware, auth_cookie
):
    _install_common_fakes(monkeypatch)

    cleared_calls: list[str] = []

    async def _fake_clear_session_messages(_db, session_id):
        cleared_calls.append(session_id)

    monkeypatch.setattr("app.routers.sessions.clear_session_messages", _fake_clear_session_messages)

    client = TestClient(app)
    response = client.post("/api/sessions/session-1/clear", cookies=auth_cookie)
    assert response.status_code == 200
    assert cleared_calls == ["session-1"]
    app.dependency_overrides.clear()


def test_archive_current_session_does_not_create_new_session_and_redirects(
    monkeypatch, patch_auth_middleware, auth_cookie
):
    # Desde ef4b7fb, archive_session_route ya no crea una sesión de respaldo explícita:
    # solo archiva y redirige a /chat. get_or_create_active_session (invocado por
    # GET /chat en app/pages/chat.py, no por esta ruta) es quien resuelve el fallback
    # -sesión existente más reciente, o una nueva solo si no queda ninguna- del lado
    # del cliente al seguir el HX-Redirect.
    _install_common_fakes(monkeypatch)
    calls: dict[str, object] = {}

    async def _fake_archive_session(_db, session_id):
        calls["archived"] = session_id

    async def _fake_create_session(_db, _user_id, channel="web"):
        raise AssertionError("archive_session_route no debe crear una sesión nueva")

    monkeypatch.setattr("app.routers.sessions.archive_session", _fake_archive_session)
    monkeypatch.setattr("app.routers.sessions.create_session", _fake_create_session)

    client = TestClient(app)
    response = client.post(
        "/api/sessions/session-1/archive",
        cookies=auth_cookie,
        data={"current_session_id": "session-1"},
    )
    assert response.status_code == 200
    assert response.headers["hx-redirect"] == "/chat"
    assert calls["archived"] == "session-1"
    app.dependency_overrides.clear()


def test_archive_non_current_session_returns_empty_partial_without_redirect(
    monkeypatch, patch_auth_middleware, auth_cookie
):
    _install_common_fakes(monkeypatch)
    calls: dict[str, object] = {}

    async def _fake_archive_session(_db, session_id):
        calls["archived"] = session_id

    async def _fake_create_session(_db, _user_id, channel="web"):
        raise AssertionError("should not create a new session for a non-current archive")

    monkeypatch.setattr("app.routers.sessions.archive_session", _fake_archive_session)
    monkeypatch.setattr("app.routers.sessions.create_session", _fake_create_session)

    client = TestClient(app)
    response = client.post(
        "/api/sessions/session-1/archive",
        cookies=auth_cookie,
        data={"current_session_id": "some-other-session"},
    )
    assert response.status_code == 200
    assert "hx-redirect" not in response.headers
    assert response.text == ""
    assert calls["archived"] == "session-1"
    app.dependency_overrides.clear()


def test_delete_current_session_cleans_checkpointer_and_redirects_without_creating_session(
    monkeypatch, patch_auth_middleware, auth_cookie
):
    # Desde ef4b7fb, delete_session_route ya no crea una sesión de respaldo explícita:
    # solo limpia el checkpointer, hace el hard-delete y redirige a /chat. Igual que en
    # archive, get_or_create_active_session (invocado por GET /chat, no por esta ruta)
    # es quien resuelve el fallback del lado del cliente al seguir el HX-Redirect.
    _install_common_fakes(monkeypatch)
    calls: list[str] = []

    class _FakeCheckpointer:
        async def adelete_thread(self, thread_id):
            calls.append(f"checkpointer:{thread_id}")

    async def _fake_get_checkpointer():
        return _FakeCheckpointer()

    async def _fake_delete_session(_db, session_id):
        calls.append(f"agent_sessions:{session_id}")

    async def _fake_create_session(_db, _user_id, channel="web"):
        raise AssertionError("delete_session_route no debe crear una sesión nueva")

    monkeypatch.setattr("app.routers.sessions.get_checkpointer", _fake_get_checkpointer)
    monkeypatch.setattr("app.routers.sessions.delete_session", _fake_delete_session)
    monkeypatch.setattr("app.routers.sessions.create_session", _fake_create_session)

    client = TestClient(app)
    response = client.post(
        "/api/sessions/session-1/delete",
        cookies=auth_cookie,
        data={"current_session_id": "session-1"},
    )
    assert response.status_code == 200
    assert response.headers["hx-redirect"] == "/chat"
    # El checkpointer se limpia antes del hard-delete de agent_sessions.
    assert calls == ["checkpointer:session-1", "agent_sessions:session-1"]
    app.dependency_overrides.clear()


def test_delete_non_current_session_returns_empty_partial(monkeypatch, patch_auth_middleware, auth_cookie):
    _install_common_fakes(monkeypatch)
    calls: dict[str, object] = {}

    class _FakeCheckpointer:
        async def adelete_thread(self, thread_id):
            calls["checkpointer"] = thread_id

    async def _fake_get_checkpointer():
        return _FakeCheckpointer()

    async def _fake_delete_session(_db, session_id):
        calls["deleted"] = session_id

    monkeypatch.setattr("app.routers.sessions.get_checkpointer", _fake_get_checkpointer)
    monkeypatch.setattr("app.routers.sessions.delete_session", _fake_delete_session)

    client = TestClient(app)
    response = client.post(
        "/api/sessions/session-1/delete",
        cookies=auth_cookie,
        data={"current_session_id": "some-other-session"},
    )
    assert response.status_code == 200
    assert "hx-redirect" not in response.headers
    assert response.text == ""
    assert calls["deleted"] == "session-1"
    app.dependency_overrides.clear()


def test_delete_session_proceeds_when_checkpointer_cleanup_fails(
    monkeypatch, patch_auth_middleware, auth_cookie
):
    _install_common_fakes(monkeypatch)
    calls: dict[str, object] = {}

    async def _fake_get_checkpointer():
        raise RuntimeError("checkpointer unavailable")

    async def _fake_delete_session(_db, session_id):
        calls["deleted"] = session_id

    monkeypatch.setattr("app.routers.sessions.get_checkpointer", _fake_get_checkpointer)
    monkeypatch.setattr("app.routers.sessions.delete_session", _fake_delete_session)

    client = TestClient(app)
    response = client.post(
        "/api/sessions/session-1/delete",
        cookies=auth_cookie,
        data={"current_session_id": "some-other-session"},
    )
    assert response.status_code == 200
    assert calls["deleted"] == "session-1"
    app.dependency_overrides.clear()
