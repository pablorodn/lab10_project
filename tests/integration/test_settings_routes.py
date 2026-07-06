from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.agent.model import FALLBACK_CHAT_MODEL, PRIMARY_CHAT_MODEL
from app.dependencies import get_current_user_id, get_db
from app.main import app


def test_settings_get_loads_real_data(monkeypatch, patch_auth_middleware, auth_cookie):
    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    async def _fake_get_profile(_db, _user_id):
        return SimpleNamespace(name="Pablo", agent_name="Atlas", agent_system_prompt="Hola")

    async def _fake_enabled_tools(_db, _user_id):
        return ["read_file"]

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id
    monkeypatch.setattr("app.pages.settings.get_profile", _fake_get_profile)
    monkeypatch.setattr("app.pages.settings.list_enabled_tool_ids", _fake_enabled_tools)

    client = TestClient(app)
    response = client.get("/settings", cookies=auth_cookie)
    assert response.status_code == 200
    assert "Atlas" in response.text
    assert "Herramientas" in response.text
    assert 'href="/settings"' in response.text
    assert "bg-blue-50 text-blue-700" in response.text
    app.dependency_overrides.clear()


def test_settings_post_persists_profile_and_tools(
    monkeypatch, patch_auth_middleware, auth_cookie
):
    calls: dict[str, object] = {}

    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    async def _fake_upsert_profile(_db, payload):
        calls["profile"] = payload
        return SimpleNamespace(**payload)

    async def _fake_replace_enabled_tools(_db, user_id, tool_ids):
        calls["tools"] = {"user_id": user_id, "tool_ids": tool_ids}

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id
    monkeypatch.setattr("app.pages.settings.upsert_profile", _fake_upsert_profile)
    monkeypatch.setattr("app.pages.settings.replace_enabled_tools", _fake_replace_enabled_tools)

    client = TestClient(app)
    response = client.post(
        "/settings",
        cookies=auth_cookie,
        data={
            "name": "Pablo",
            "agent_name": "Atlas",
            "system_prompt": "Ayuda",
            "enabled_tools": ["read_file", "invalid_tool"],
        },
    )
    assert response.status_code == 200
    assert "Guardado correctamente." in response.text
    assert calls["profile"]["agent_name"] == "Atlas"
    assert calls["tools"] == {"user_id": "user-1", "tool_ids": ["read_file"]}
    app.dependency_overrides.clear()


def test_settings_get_shows_stored_model_selected(monkeypatch, patch_auth_middleware, auth_cookie):
    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    async def _fake_get_profile(_db, _user_id):
        return SimpleNamespace(
            name="Pablo", agent_name="Atlas", agent_system_prompt="Hola", default_model=FALLBACK_CHAT_MODEL
        )

    async def _fake_enabled_tools(_db, _user_id):
        return []

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id
    monkeypatch.setattr("app.pages.settings.get_profile", _fake_get_profile)
    monkeypatch.setattr("app.pages.settings.list_enabled_tool_ids", _fake_enabled_tools)

    client = TestClient(app)
    response = client.get("/settings", cookies=auth_cookie)
    assert response.status_code == 200
    assert f'value="{FALLBACK_CHAT_MODEL}" selected' in response.text
    app.dependency_overrides.clear()


def test_settings_get_revalidates_stale_stored_model(monkeypatch, patch_auth_middleware, auth_cookie):
    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    async def _fake_get_profile(_db, _user_id):
        return SimpleNamespace(
            name="Pablo", agent_name="Atlas", agent_system_prompt="Hola", default_model="retired-model"
        )

    async def _fake_enabled_tools(_db, _user_id):
        return []

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id
    monkeypatch.setattr("app.pages.settings.get_profile", _fake_get_profile)
    monkeypatch.setattr("app.pages.settings.list_enabled_tool_ids", _fake_enabled_tools)

    client = TestClient(app)
    response = client.get("/settings", cookies=auth_cookie)
    assert response.status_code == 200
    assert f'value="{PRIMARY_CHAT_MODEL}" selected' in response.text
    app.dependency_overrides.clear()


def test_settings_post_persists_valid_default_model(monkeypatch, patch_auth_middleware, auth_cookie):
    calls: dict[str, object] = {}

    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    async def _fake_upsert_profile(_db, payload):
        calls["profile"] = payload
        return SimpleNamespace(**payload)

    async def _fake_replace_enabled_tools(_db, _user_id, _tool_ids):
        return None

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id
    monkeypatch.setattr("app.pages.settings.upsert_profile", _fake_upsert_profile)
    monkeypatch.setattr("app.pages.settings.replace_enabled_tools", _fake_replace_enabled_tools)

    client = TestClient(app)
    response = client.post(
        "/settings",
        cookies=auth_cookie,
        data={
            "name": "Pablo",
            "agent_name": "Atlas",
            "system_prompt": "Ayuda",
            "default_model": FALLBACK_CHAT_MODEL,
        },
    )
    assert response.status_code == 200
    assert calls["profile"]["default_model"] == FALLBACK_CHAT_MODEL
    app.dependency_overrides.clear()


def test_settings_post_ignores_unknown_default_model(monkeypatch, patch_auth_middleware, auth_cookie, caplog):
    calls: dict[str, object] = {}

    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    async def _fake_upsert_profile(_db, payload):
        calls["profile"] = payload
        return SimpleNamespace(**payload)

    async def _fake_replace_enabled_tools(_db, _user_id, _tool_ids):
        return None

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id
    monkeypatch.setattr("app.pages.settings.upsert_profile", _fake_upsert_profile)
    monkeypatch.setattr("app.pages.settings.replace_enabled_tools", _fake_replace_enabled_tools)

    client = TestClient(app)
    with caplog.at_level("WARNING", logger="app.agent.model"):
        response = client.post(
            "/settings",
            cookies=auth_cookie,
            data={
                "name": "Pablo",
                "agent_name": "Atlas",
                "system_prompt": "Ayuda",
                "default_model": "retired-model",
            },
        )
    assert response.status_code == 200
    assert "default_model" not in calls["profile"]
    assert any(r.message.startswith("Requested chat model") for r in caplog.records)
    app.dependency_overrides.clear()
