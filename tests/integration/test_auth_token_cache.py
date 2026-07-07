from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.dependencies import get_current_user_id, get_db
from app.main import app


def _install_fake_auth(monkeypatch, *, call_count: dict):
    class _FakeUser:
        def model_dump(self):
            return {"id": "user-1"}

    class _FakeAuth:
        async def get_user(self, _token: str):
            call_count["get_user"] += 1

            class _Response:
                user = _FakeUser()

            return _Response()

    class _FakeClient:
        auth = _FakeAuth()

    async def _fake_create_server_client():
        return _FakeClient()

    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    async def _fake_get_profile(_db, _user_id):
        return SimpleNamespace(onboarding_completed=True)

    monkeypatch.setattr("app.middleware.auth.create_server_client", _fake_create_server_client)
    monkeypatch.setattr("app.pages.index.get_profile", _fake_get_profile)
    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id


def test_second_request_with_same_token_skips_supabase_auth_call(monkeypatch):
    call_count = {"get_user": 0}
    _install_fake_auth(monkeypatch, call_count=call_count)
    client = TestClient(app)
    cookies = {"sb-access-token": "same-token-across-requests"}

    try:
        first = client.get("/", cookies=cookies, follow_redirects=False)
        second = client.get("/", cookies=cookies, follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 307
    assert second.status_code == 307
    assert call_count["get_user"] == 1


def test_different_tokens_each_trigger_their_own_supabase_auth_call(monkeypatch):
    call_count = {"get_user": 0}
    _install_fake_auth(monkeypatch, call_count=call_count)
    client = TestClient(app)

    try:
        first = client.get("/", cookies={"sb-access-token": "token-a"}, follow_redirects=False)
        second = client.get("/", cookies={"sb-access-token": "token-b"}, follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert first.status_code == 307
    assert second.status_code == 307
    assert call_count["get_user"] == 2
