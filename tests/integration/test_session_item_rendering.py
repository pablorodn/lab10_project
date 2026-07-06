from types import SimpleNamespace

from fastapi.templating import Jinja2Templates

from app.template_filters import register_template_filters

templates = Jinja2Templates(directory="app/templates")
register_template_filters(templates)


def _render(session, current_session_id=None):
    tpl = templates.get_template("partials/session_item.html")
    return tpl.render({"request": None, "session": session, "current_session_id": current_session_id})


def test_session_item_falls_back_to_date_when_title_is_null():
    session = SimpleNamespace(
        id="session-1", title=None, last_used_at="2026-07-05T10:00:00+00:00"
    )
    html = _render(session)
    assert "session-1" in html
    assert "Nueva sesión" not in html
    # El filtro format_session_date se aplica sobre last_used_at como fallback.
    assert "5 jul, 10:00" in html


def test_session_item_falls_back_to_new_session_label_when_no_title_and_no_date():
    session = SimpleNamespace(id="session-1", title=None, last_used_at=None)
    html = _render(session)
    assert "Nueva sesión" in html


def test_session_item_shows_title_when_present():
    session = SimpleNamespace(
        id="session-1", title="Planear viaje a Japon", last_used_at="2026-07-05T10:00:00+00:00"
    )
    html = _render(session)
    assert "Planear viaje a Japon" in html


def test_session_item_includes_archive_and_delete_actions_with_correct_confirm_behavior():
    session = SimpleNamespace(id="session-42", title=None, last_used_at=None)
    html = _render(session, current_session_id="session-42")
    assert "/api/sessions/session-42/archive" in html
    assert "/api/sessions/session-42/delete" in html
    assert "¿Eliminar esta conversación? Esta acción no se puede deshacer." in html

    archive_button = html.split("/api/sessions/session-42/archive")[1].split("</button>")[0]
    delete_button = html.split("/api/sessions/session-42/delete")[1].split("</button>")[0]
    assert "hx-confirm" not in archive_button
    assert "hx-confirm" in delete_button
