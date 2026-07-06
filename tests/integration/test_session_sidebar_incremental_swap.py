"""Fase 4 (Bloque C, fix #5): antes, cambiar/crear una sesion reconstruia
la lista completa de sesiones via un OOB swap de partials/session_list.html
entero (contradiciendo docs/ui-design.md, que documenta swap incremental).
Ahora POST /api/sessions y GET /chat/session/{id} solo emiten OOB swaps para
el item que deja de estar activo (des-resaltado) y el item que pasa a estarlo
(resaltado o insertado), sin volver a listar ni re-renderizar el resto de
sesiones.
"""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.dependencies import get_current_user_id, get_db
from app.main import app


def test_create_session_only_swaps_previous_and_new_item_not_full_list(
    monkeypatch, patch_auth_middleware, auth_cookie
):
    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    new_session = SimpleNamespace(id="session-new", title=None, last_used_at=None)
    old_session = SimpleNamespace(id="session-old", title="Charla previa", last_used_at=None)

    async def _fake_create_session(_db, _user_id, channel="web"):
        return new_session

    async def _fake_get_session_by_id(_db, session_id):
        assert session_id == "session-old"
        return old_session

    async def _fake_profile(_db, _user_id):
        return SimpleNamespace(agent_name="Atlas")

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id
    monkeypatch.setattr("app.routers.sessions.create_session", _fake_create_session)
    monkeypatch.setattr("app.routers.sessions.get_session_by_id", _fake_get_session_by_id)
    monkeypatch.setattr("app.routers.sessions.get_profile", _fake_profile)

    async def _fail_list_sessions(*_args, **_kwargs):
        raise AssertionError(
            "post_session no deberia volver a listar todas las sesiones: el swap es incremental"
        )

    monkeypatch.setattr("app.routers.sessions.list_sessions", _fail_list_sessions)

    client = TestClient(app)
    response = client.post(
        "/api/sessions", cookies=auth_cookie, data={"current_session_id": "session-old"}
    )
    assert response.status_code == 200
    body = response.text

    assert 'id="session-item-session-new"' in body
    assert 'hx-swap-oob="afterbegin:#session-list"' in body

    assert 'id="session-item-session-old"' in body
    assert "Charla previa" in body
    old_item = body.split('id="session-item-session-old"')[1].split("</div>\n</div>")[0]
    assert 'hx-swap-oob="true"' in body.split('id="session-item-session-old"')[1][:200]
    assert "bg-blue-50 text-blue-700" not in old_item.split("</button>")[0]

    assert 'hx-swap-oob="delete"' in body
    assert 'id="session-list-empty"' in body
    app.dependency_overrides.clear()


def test_switch_session_only_swaps_previous_and_new_item_not_full_list(
    monkeypatch, patch_auth_middleware, auth_cookie
):
    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    active_session = SimpleNamespace(
        id="session-2", user_id="user-1", title="Sesion activa", last_used_at=None
    )
    previous_session = SimpleNamespace(
        id="session-1", user_id="user-1", title="Sesion anterior", last_used_at=None
    )

    async def _fake_get_session_by_id(_db, session_id):
        if session_id == "session-2":
            return active_session
        if session_id == "session-1":
            return previous_session
        return None

    async def _fake_touch(_db, _session_id):
        return None

    async def _fake_messages(_db, _session_id):
        return []

    async def _fake_pending(_db, _session_id):
        return False

    async def _fake_profile(_db, _user_id):
        return SimpleNamespace(agent_name="Atlas")

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id
    monkeypatch.setattr("app.pages.chat.get_session_by_id", _fake_get_session_by_id)
    monkeypatch.setattr("app.pages.chat.touch_session", _fake_touch)
    monkeypatch.setattr("app.pages.chat.get_session_messages", _fake_messages)
    monkeypatch.setattr("app.pages.chat.has_pending_confirmation_for_session", _fake_pending)
    monkeypatch.setattr("app.pages.chat.get_profile", _fake_profile)

    async def _fail_list_sessions(*_args, **_kwargs):
        raise AssertionError(
            "chat_session no deberia volver a listar todas las sesiones: el swap es incremental"
        )

    monkeypatch.setattr("app.pages.chat.list_sessions", _fail_list_sessions)

    client = TestClient(app)
    response = client.get(
        "/chat/session/session-2",
        cookies=auth_cookie,
        params={"current_session_id": "session-1"},
    )
    assert response.status_code == 200
    body = response.text

    assert "Sesion activa" in body
    assert "Sesion anterior" in body

    new_item = body.split('id="session-item-session-2"')[1].split("</div>\n</div>")[0]
    assert "bg-blue-50 text-blue-700" in new_item.split("</button>")[0]

    old_item = body.split('id="session-item-session-1"')[1].split("</div>\n</div>")[0]
    assert "bg-blue-50 text-blue-700" not in old_item.split("</button>")[0]

    assert body.count('id="session-item-') == 2
    app.dependency_overrides.clear()
