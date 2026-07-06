from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.dependencies import get_current_user_id, get_db
from app.main import app


def test_onboarding_step_tools_persists_in_session(
    monkeypatch, patch_auth_middleware, auth_cookie
):
    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    async def _fake_get_profile(_db, _user_id):
        return SimpleNamespace(onboarding_completed=False)

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id
    monkeypatch.setattr("app.pages.onboarding.get_profile", _fake_get_profile)

    client = TestClient(app)
    response = client.post(
        "/onboarding/step/2",
        cookies=auth_cookie,
        data={"enabled_tools": ["read_file", "write_file"]},
    )
    assert response.status_code == 200

    review = client.get("/onboarding/step/3", cookies=auth_cookie)
    assert review.status_code == 200
    assert "read_file" in review.text
    assert "write_file" in review.text
    # Fase 4 (Bloque F): la navegacion entre pasos ya no reemplaza <body>
    # entero (perdiendo scroll/foco); ahora hace swap incremental solo del
    # contenedor id="onboarding-wizard" (nav de pasos + card + botones),
    # extraido de la respuesta completa via hx-select.
    assert 'id="onboarding-wizard"' in review.text
    assert 'hx-target="#onboarding-wizard"' in review.text
    assert 'hx-select="#onboarding-wizard"' in review.text
    assert 'hx-swap="outerHTML"' in review.text
    assert 'hx-target="body"' not in review.text
    app.dependency_overrides.clear()


def test_onboarding_finish_persists_profile_and_tools(
    monkeypatch, patch_auth_middleware, auth_cookie
):
    calls: dict[str, object] = {}

    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    async def _fake_get_profile(_db, _user_id):
        return SimpleNamespace(onboarding_completed=False)

    async def _fake_upsert_profile(_db, payload):
        calls["profile"] = payload
        return SimpleNamespace(**payload)

    async def _fake_replace_enabled_tools(_db, user_id, tool_ids):
        calls["tools"] = {"user_id": user_id, "tool_ids": tool_ids}

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id
    monkeypatch.setattr("app.pages.onboarding.get_profile", _fake_get_profile)
    monkeypatch.setattr("app.pages.onboarding.upsert_profile", _fake_upsert_profile)
    monkeypatch.setattr("app.pages.onboarding.replace_enabled_tools", _fake_replace_enabled_tools)

    client = TestClient(app)
    client.post(
        "/onboarding/step/0",
        cookies=auth_cookie,
        data={"name": "Pablo", "timezone": "America/Bogota", "language": "es"},
    )
    client.post(
        "/onboarding/step/1",
        cookies=auth_cookie,
        data={"agent_name": "Agente P", "system_prompt": "ayuda"},
    )
    client.post(
        "/onboarding/step/2",
        cookies=auth_cookie,
        data={"enabled_tools": ["read_file", "write_file"]},
    )
    response = client.post("/onboarding/finish", cookies=auth_cookie)
    assert response.status_code == 200
    assert response.headers["hx-redirect"] == "/chat"
    assert calls["profile"]["onboarding_completed"] is True
    assert calls["tools"] == {"user_id": "user-1", "tool_ids": ["read_file", "write_file"]}
    app.dependency_overrides.clear()


def test_onboarding_redirects_to_chat_when_completed(
    monkeypatch, patch_auth_middleware, auth_cookie
):
    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    async def _fake_get_profile(_db, _user_id):
        return SimpleNamespace(onboarding_completed=True)

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id
    monkeypatch.setattr("app.pages.onboarding.get_profile", _fake_get_profile)
    client = TestClient(app)
    response = client.get("/onboarding", cookies=auth_cookie, follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/chat"
    app.dependency_overrides.clear()
