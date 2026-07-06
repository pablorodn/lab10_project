from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from supabase import AsyncClient
from supabase_auth.errors import AuthApiError

from app.config import get_settings
from app.db.client import create_server_client

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


async def _db() -> AsyncClient:
    return await create_server_client()


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "auth/login.html", {"request": request, "error": None})


@router.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    return templates.TemplateResponse(request, "auth/signup.html", {"request": request, "error": None})


@router.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncClient = Depends(_db),
):
    try:
        result = await db.auth.sign_in_with_password({"email": email, "password": password})
    except AuthApiError:
        return templates.TemplateResponse(
            request, "partials/login_form.html", {"request": request, "error": "Credenciales inválidas"}
        )
    if result.user and result.session:
        response = HTMLResponse(status_code=200)
        response.headers["HX-Redirect"] = "/"
        secure_cookies = get_settings().is_production
        response.set_cookie("sb-access-token", result.session.access_token, httponly=True, secure=secure_cookies)
        response.set_cookie("sb-refresh-token", result.session.refresh_token, httponly=True, secure=secure_cookies)
        return response
    return templates.TemplateResponse(
        request, "partials/login_form.html", {"request": request, "error": "Credenciales inválidas"}
    )


@router.post("/signup", response_class=HTMLResponse)
async def signup(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncClient = Depends(_db),
):
    try:
        result = await db.auth.sign_up({"email": email, "password": password})
    except AuthApiError as exc:
        message = str(exc)
        if "User already registered" in message:
            return templates.TemplateResponse(
                request,
                "partials/signup_form.html",
                {"request": request, "error": "Este correo ya está registrado. Inicia sesión."},
            )
        return templates.TemplateResponse(
            request,
            "partials/signup_form.html",
            {"request": request, "error": "No se pudo crear la cuenta"},
        )
    if result.user:
        session = result.session
        # Some Supabase projects require email confirmation before automatic session creation.
        # Try password sign-in to obtain a session when possible.
        if session is None:
            try:
                signin_result = await db.auth.sign_in_with_password({"email": email, "password": password})
                session = signin_result.session
            except Exception:
                session = None
        if session:
            response = HTMLResponse(status_code=200)
            response.headers["HX-Redirect"] = "/onboarding"
            secure_cookies = get_settings().is_production
            response.set_cookie("sb-access-token", session.access_token, httponly=True, secure=secure_cookies)
            response.set_cookie("sb-refresh-token", session.refresh_token, httponly=True, secure=secure_cookies)
            return response
        return templates.TemplateResponse(
            request,
            "partials/signup_form.html",
            {
                "request": request,
                "error": "Cuenta creada. Revisa tu correo para confirmar y luego inicia sesión.",
            },
        )
    return templates.TemplateResponse(
        request, "partials/signup_form.html", {"request": request, "error": "No se pudo crear la cuenta"}
    )


@router.post("/logout")
async def logout():
    response = HTMLResponse(status_code=200)
    response.headers["HX-Redirect"] = "/login"
    response.delete_cookie("sb-access-token")
    response.delete_cookie("sb-refresh-token")
    return response

