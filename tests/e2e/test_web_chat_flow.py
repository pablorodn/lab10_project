from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.dependencies import get_current_user_id, get_db
from app.main import app


def test_root_redirects_to_login_without_cookie():
    client = TestClient(app)
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (307, 302)
    assert response.headers["location"] == "/login"


def test_topbar_visible_in_authenticated_pages(
    monkeypatch, patch_auth_middleware, auth_cookie
):
    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    async def _fake_list_sessions(_db, user_id: str, channel: str = "web"):
        _ = (user_id, channel)
        return []

    async def _fake_session(_db, user_id: str, channel: str):
        _ = (user_id, channel)
        return SimpleNamespace(id="session-1")

    async def _fake_touch(_db, session_id: str):
        _ = session_id

    async def _fake_messages(_db, session_id: str):
        _ = session_id
        return []

    async def _fake_profile(_db, _user_id):
        return SimpleNamespace(name="Pablo", agent_name="Atlas", agent_system_prompt="Hola")

    async def _fake_pending(_db, _session_id):
        return False

    async def _fake_tools(_db, _user_id):
        return []

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id
    monkeypatch.setattr("app.pages.chat.get_or_create_active_session", _fake_session)
    monkeypatch.setattr("app.pages.chat.list_sessions", _fake_list_sessions)
    monkeypatch.setattr("app.pages.chat.touch_session", _fake_touch)
    monkeypatch.setattr("app.pages.chat.get_session_messages", _fake_messages)
    monkeypatch.setattr("app.pages.chat.get_profile", _fake_profile)
    monkeypatch.setattr("app.pages.chat.has_pending_confirmation_for_session", _fake_pending)
    monkeypatch.setattr("app.pages.settings.get_profile", _fake_profile)
    monkeypatch.setattr("app.pages.settings.list_enabled_tool_ids", _fake_tools)

    client = TestClient(app)
    chat_response = client.get("/chat", cookies=auth_cookie)
    settings_response = client.get("/settings", cookies=auth_cookie)
    assert chat_response.status_code == 200
    assert settings_response.status_code == 200
    assert "Ajustes" in chat_response.text
    assert "Salir" in settings_response.text
    assert 'href="/chat"' in chat_response.text
    assert "bg-blue-50 text-blue-700" in chat_response.text
    assert 'href="/settings"' in settings_response.text
    assert "bg-blue-50 text-blue-700" in settings_response.text
    app.dependency_overrides.clear()
