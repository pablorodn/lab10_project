from types import SimpleNamespace

from fastapi.testclient import TestClient
from supabase_auth.errors import AuthApiError

from app.config import get_settings
from app.dependencies import get_current_user_id, get_db
from app.main import app
from app.middleware.token_cache import cache_token, get_cached_user_id
from app.routers import auth as auth_router


def test_login_page_renders():
    client = TestClient(app)
    response = client.get("/login")
    assert response.status_code == 200
    assert "Iniciar sesión" in response.text


def test_signup_page_renders():
    client = TestClient(app)
    response = client.get("/signup")
    assert response.status_code == 200
    assert "Crear cuenta" in response.text


def test_signup_existing_user_returns_form_error_not_500():
    class _FakeAuth:
        async def sign_up(self, _payload):
            raise AuthApiError("User already registered", 422, None)

    class _FakeDB:
        auth = _FakeAuth()

    async def _fake_db():
        return _FakeDB()

    app.dependency_overrides[auth_router._db] = _fake_db
    client = TestClient(app)
    response = client.post(
        "/signup",
        data={"email": "existing@example.com", "password": "123456"},
    )
    assert response.status_code == 200
    assert "ya está registrado" in response.text
    app.dependency_overrides.clear()


def test_signup_happy_path_keeps_hx_redirect():
    class _FakeSession:
        access_token = "access-token"
        refresh_token = "refresh-token"

    class _FakeResult:
        user = object()
        session = _FakeSession()

    class _FakeAuth:
        async def sign_up(self, _payload):
            return _FakeResult()

    class _FakeDB:
        auth = _FakeAuth()

    async def _fake_db():
        return _FakeDB()

    app.dependency_overrides[auth_router._db] = _fake_db
    client = TestClient(app)
    response = client.post(
        "/signup",
        data={"email": "new@example.com", "password": "123456"},
    )
    assert response.status_code == 200
    assert response.headers["hx-redirect"] == "/onboarding"
    assert "sb-access-token=" in response.headers.get("set-cookie", "")
    app.dependency_overrides.clear()


def _install_fake_login(app_, *, monkeypatch=None):
    class _FakeSession:
        access_token = "access-token"
        refresh_token = "refresh-token"

    class _FakeResult:
        user = object()
        session = _FakeSession()

    class _FakeAuth:
        async def sign_in_with_password(self, _payload):
            return _FakeResult()

    class _FakeDB:
        auth = _FakeAuth()

    async def _fake_db():
        return _FakeDB()

    app_.dependency_overrides[auth_router._db] = _fake_db


def test_login_wrong_password_returns_form_error_not_500():
    class _FakeAuth:
        async def sign_in_with_password(self, _payload):
            raise AuthApiError("Invalid login credentials", 400, None)

    class _FakeDB:
        auth = _FakeAuth()

    async def _fake_db():
        return _FakeDB()

    app.dependency_overrides[auth_router._db] = _fake_db
    client = TestClient(app)
    response = client.post(
        "/login",
        data={"email": "a@b.com", "password": "wrong-password"},
    )
    assert response.status_code == 200
    assert "Credenciales inválidas" in response.text
    app.dependency_overrides.clear()


def test_login_cookies_not_secure_by_default():
    _install_fake_login(app)
    client = TestClient(app)
    response = client.post("/login", data={"email": "a@b.com", "password": "123456"})
    # Bloque B3 (Fase 5): faltaba verificar el contrato HTMX del login
    # exitoso, no solo el flag `secure` de las cookies.
    assert response.headers["hx-redirect"] == "/"
    set_cookie_headers = response.headers.get_list("set-cookie")
    assert set_cookie_headers
    assert not any("secure" in header.lower() for header in set_cookie_headers)
    app.dependency_overrides.clear()


def test_login_cookies_secure_when_environment_is_production(monkeypatch):
    _install_fake_login(app)

    class _ProductionSettings:
        is_production = True

    monkeypatch.setattr("app.routers.auth.get_settings", lambda: _ProductionSettings())
    client = TestClient(app)
    response = client.post("/login", data={"email": "a@b.com", "password": "123456"})
    assert response.headers["hx-redirect"] == "/"
    set_cookie_headers = response.headers.get_list("set-cookie")
    assert set_cookie_headers
    assert all("secure" in header.lower() for header in set_cookie_headers)
    app.dependency_overrides.clear()


def test_index_redirects_to_onboarding_when_incomplete(
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
    monkeypatch.setattr("app.pages.index.get_profile", _fake_get_profile)
    client = TestClient(app)
    response = client.get("/", cookies=auth_cookie, follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/onboarding"
    app.dependency_overrides.clear()


def test_index_redirects_to_chat_when_completed(
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
    monkeypatch.setattr("app.pages.index.get_profile", _fake_get_profile)
    client = TestClient(app)
    response = client.get("/", cookies=auth_cookie, follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/chat"
    app.dependency_overrides.clear()


def test_auth_middleware_refreshes_expired_access_token_and_continues_request(monkeypatch):
    class _FakeUser:
        def model_dump(self):
            return {"id": "user-1"}

    class _RefreshSession:
        access_token = "new-access-token"
        refresh_token = "new-refresh-token"

    class _RefreshResult:
        user = _FakeUser()
        session = _RefreshSession()

    class _FakeAuth:
        async def get_user(self, token: str):
            if token == "expired-access-token":
                raise RuntimeError("JWT expired")

            class _Response:
                user = _FakeUser()

            return _Response()

        async def refresh_session(self, refresh_token: str):
            assert refresh_token == "valid-refresh-token"
            return _RefreshResult()

    class _FakeClient:
        auth = _FakeAuth()

    async def _fake_create_server_client():
        return _FakeClient()

    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    async def _fake_get_profile(_db, _user_id):
        return SimpleNamespace(onboarding_completed=False)

    monkeypatch.setattr("app.middleware.auth.create_server_client", _fake_create_server_client)
    monkeypatch.setattr("app.pages.index.get_profile", _fake_get_profile)
    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id

    client = TestClient(app)
    response = client.get(
        "/",
        cookies={
            "sb-access-token": "expired-access-token",
            "sb-refresh-token": "valid-refresh-token",
        },
        follow_redirects=False,
    )
    assert response.status_code == 307
    assert response.headers["location"] == "/onboarding"
    set_cookie = response.headers.get("set-cookie", "")
    assert "sb-access-token=new-access-token" in set_cookie
    assert "sb-refresh-token=new-refresh-token" in set_cookie
    app.dependency_overrides.clear()


def test_auth_middleware_redirects_to_login_when_access_and_refresh_tokens_both_invalid(
    monkeypatch, caplog
):
    """Bloque B2 (Fase 5): todos los tests de "sesion expirada" existentes
    (arriba) modelan un access-token vencido CON refresh_token valido (el
    refresh tiene exito). Ninguno ejercita el branch real de sesion
    REALMENTE expirada: refresh_session() tambien falla/no devuelve sesion
    (app/middleware/auth.py:63-68, reason="invalid_or_expired_token")."""

    class _FakeAuth:
        async def get_user(self, _token: str):
            raise RuntimeError("JWT expired")

        async def refresh_session(self, _refresh_token: str):
            class _FailedRefreshResponse:
                session = None
                user = None

            return _FailedRefreshResponse()

    class _FakeClient:
        auth = _FakeAuth()

    async def _fake_create_server_client():
        return _FakeClient()

    monkeypatch.setattr("app.middleware.auth.create_server_client", _fake_create_server_client)

    client = TestClient(app)
    with caplog.at_level("INFO", logger="app.middleware.auth"):
        response = client.get(
            "/",
            cookies={
                "sb-access-token": "expired-access-token",
                "sb-refresh-token": "also-expired-refresh-token",
            },
            follow_redirects=False,
        )

    assert response.status_code == 307
    assert response.headers["location"] == "/login"
    # No debe rotar cookies: la sesion no se pudo recuperar de ninguna forma.
    assert not response.headers.get_list("set-cookie")
    matching_records = [
        r for r in caplog.records if getattr(r, "reason", None) == "invalid_or_expired_token"
    ]
    assert matching_records


def _install_fake_refresh_middleware(monkeypatch):
    class _FakeUser:
        def model_dump(self):
            return {"id": "user-1"}

    class _RefreshSession:
        access_token = "rotated-access-token"
        refresh_token = "rotated-refresh-token"

    class _RefreshResult:
        user = _FakeUser()
        session = _RefreshSession()

    class _FakeAuth:
        async def get_user(self, _token: str):
            raise RuntimeError("JWT expired")

        async def refresh_session(self, refresh_token: str):
            assert refresh_token == "valid-refresh-token"
            return _RefreshResult()

    class _FakeClient:
        auth = _FakeAuth()

    async def _fake_create_server_client():
        return _FakeClient()

    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    async def _fake_get_profile(_db, _user_id):
        return SimpleNamespace(onboarding_completed=False)

    monkeypatch.setattr("app.middleware.auth.create_server_client", _fake_create_server_client)
    monkeypatch.setattr("app.pages.index.get_profile", _fake_get_profile)
    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id


def _rotated_set_cookie_headers(response) -> list[str]:
    return [
        header
        for header in response.headers.get_list("set-cookie")
        if header.startswith("sb-access-token=") or header.startswith("sb-refresh-token=")
    ]


def test_auth_middleware_rotated_cookies_not_secure_by_default(monkeypatch):
    _install_fake_refresh_middleware(monkeypatch)
    client = TestClient(app)
    response = client.get(
        "/",
        cookies={
            "sb-access-token": "expired-access-token",
            "sb-refresh-token": "valid-refresh-token",
        },
        follow_redirects=False,
    )
    rotated_headers = _rotated_set_cookie_headers(response)
    assert rotated_headers
    assert not any("secure" in header.lower() for header in rotated_headers)
    app.dependency_overrides.clear()


def test_auth_middleware_rotated_cookies_secure_when_environment_is_production(monkeypatch):
    _install_fake_refresh_middleware(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        response = client.get(
            "/",
            cookies={
                "sb-access-token": "expired-access-token",
                "sb-refresh-token": "valid-refresh-token",
            },
            follow_redirects=False,
        )
        rotated_headers = _rotated_set_cookie_headers(response)
        assert rotated_headers
        assert all("secure" in header.lower() for header in rotated_headers)
    finally:
        get_settings.cache_clear()
        app.dependency_overrides.clear()


def test_auth_middleware_logs_real_exception_reason_for_unexpected_provider_error(
    monkeypatch, caplog
):
    # create_server_client() falla antes de llegar al try/except interno de
    # validate_access_token, así que la excepción solo puede ser atrapada por el
    # except Exception genérico externo de AuthMiddleware.dispatch.
    async def _fake_create_server_client():
        raise RuntimeError("boom - unexpected supabase client failure")

    monkeypatch.setattr("app.middleware.auth.create_server_client", _fake_create_server_client)

    client = TestClient(app)
    with caplog.at_level("WARNING", logger="app.middleware.auth"):
        response = client.get(
            "/",
            cookies={"sb-access-token": "some-token"},
            follow_redirects=False,
        )
    assert response.status_code == 307
    assert response.headers["location"] == "/login"
    warning_records = [r for r in caplog.records if r.levelname == "WARNING"]
    assert warning_records
    assert any(
        getattr(record, "reason", None) == "boom - unexpected supabase client failure"
        for record in warning_records
    )


def test_logout_redirects_to_login_and_deletes_session_cookies(
    patch_auth_middleware, auth_cookie
):
    """Bloque B1 (Fase 5): POST /logout no tenia ningun test en todo el repo."""
    client = TestClient(app)
    response = client.post("/logout", cookies=auth_cookie)

    assert response.status_code == 200
    assert response.headers["hx-redirect"] == "/login"

    set_cookie_headers = response.headers.get_list("set-cookie")
    access_token_header = next(h for h in set_cookie_headers if h.startswith("sb-access-token="))
    refresh_token_header = next(h for h in set_cookie_headers if h.startswith("sb-refresh-token="))
    # delete_cookie() emite un Set-Cookie con valor vacio y expiracion en el
    # pasado (Max-Age=0) -- asi es como el browser efectivamente borra la
    # cookie, no solo la vacia de contenido.
    assert 'sb-access-token=""' in access_token_header or "sb-access-token=;" in access_token_header
    assert "Max-Age=0" in access_token_header
    assert 'sb-refresh-token=""' in refresh_token_header or "sb-refresh-token=;" in refresh_token_header
    assert "Max-Age=0" in refresh_token_header


def test_logout_invalidates_cached_access_token(patch_auth_middleware, auth_cookie):
    # CAMBIO 1: sin esto, un logout no seria efectivo hasta TOKEN_CACHE_TTL_SECONDS
    # (60s) despues -- AuthMiddleware seguiria autenticando con el token cacheado
    # aunque la cookie ya se haya borrado en el browser.
    cache_token(auth_cookie["sb-access-token"], "user-1")
    assert get_cached_user_id(auth_cookie["sb-access-token"]) == "user-1"

    client = TestClient(app)
    response = client.post("/logout", cookies=auth_cookie)

    assert response.status_code == 200
    assert get_cached_user_id(auth_cookie["sb-access-token"]) is None


def test_auth_middleware_does_not_mask_downstream_errors_as_login_redirect(
    monkeypatch, patch_auth_middleware, auth_cookie
):
    async def _fake_db():
        return object()

    async def _fake_user_id():
        return "user-1"

    async def _boom_profile(_db, _user_id):
        raise RuntimeError("downstream failure")

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_user_id] = _fake_user_id
    monkeypatch.setattr("app.pages.index.get_profile", _boom_profile)

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/", cookies=auth_cookie, follow_redirects=False)
    assert response.status_code == 500
    assert response.headers.get("location") != "/login"
    app.dependency_overrides.clear()
