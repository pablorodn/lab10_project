from types import SimpleNamespace

import pytest

from app.agent.session_title import generate_session_title


def _msg(role, content):
    return SimpleNamespace(role=role, content=content)


def _first_user_message_with_content(messages):
    """Simula el filtro SQL de get_first_user_message_with_content: primer
    mensaje de rol 'user' con contenido distinto de cadena vacía, en orden."""
    for message in messages:
        if message.role == "user" and message.content != "":
            return message
    return None


class _FakeModel:
    def __init__(self, content):
        self._content = content
        self.received_messages = None

    async def ainvoke(self, messages):
        self.received_messages = messages
        return SimpleNamespace(content=self._content)


@pytest.mark.anyio
async def test_generate_session_title_uses_first_texted_user_message(monkeypatch):
    messages = [
        _msg("user", ""),  # solo-adjuntos: sin texto
        _msg("user", "  Ayudame a planear un viaje a Japon  "),
        _msg("assistant", "Claro, contame fechas"),
    ]

    async def _fake_get_first_user_message_with_content(_db, _session_id):
        return _first_user_message_with_content(messages)

    fake_model = _FakeModel('"Planear viaje a Japon."')
    updates: list[tuple[str, str]] = []

    async def _fake_update_session_title(_db, session_id, title):
        updates.append((session_id, title))
        return True

    monkeypatch.setattr(
        "app.agent.session_title.get_first_user_message_with_content",
        _fake_get_first_user_message_with_content,
    )
    monkeypatch.setattr("app.agent.session_title.create_compaction_model", lambda max_tokens=None: fake_model)
    monkeypatch.setattr("app.agent.session_title.update_session_title", _fake_update_session_title)

    await generate_session_title(db=object(), session_id="session-1")

    assert updates == [("session-1", "Planear viaje a Japon")]
    seed_text = fake_model.received_messages[1].content
    assert "Ayudame a planear un viaje a Japon" in seed_text


@pytest.mark.anyio
async def test_generate_session_title_truncates_to_six_words(monkeypatch):
    messages = [_msg("user", "hola")]

    async def _fake_get_first_user_message_with_content(_db, _session_id):
        return _first_user_message_with_content(messages)

    fake_model = _FakeModel("Uno Dos Tres Cuatro Cinco Seis Siete Ocho")
    updates: list[tuple[str, str]] = []

    async def _fake_update_session_title(_db, session_id, title):
        updates.append((session_id, title))
        return True

    monkeypatch.setattr(
        "app.agent.session_title.get_first_user_message_with_content",
        _fake_get_first_user_message_with_content,
    )
    monkeypatch.setattr("app.agent.session_title.create_compaction_model", lambda max_tokens=None: fake_model)
    monkeypatch.setattr("app.agent.session_title.update_session_title", _fake_update_session_title)

    await generate_session_title(db=object(), session_id="session-1")

    assert updates == [("session-1", "Uno Dos Tres Cuatro Cinco Seis")]


@pytest.mark.anyio
async def test_generate_session_title_skips_when_only_attachment_messages(monkeypatch):
    messages = [_msg("user", ""), _msg("user", "   ")]
    called = {"update": False}

    async def _fake_get_first_user_message_with_content(_db, _session_id):
        return _first_user_message_with_content(messages)

    async def _fake_update_session_title(_db, _session_id, _title):
        called["update"] = True

    monkeypatch.setattr(
        "app.agent.session_title.get_first_user_message_with_content",
        _fake_get_first_user_message_with_content,
    )
    monkeypatch.setattr("app.agent.session_title.update_session_title", _fake_update_session_title)

    await generate_session_title(db=object(), session_id="session-1")

    assert called["update"] is False


@pytest.mark.anyio
async def test_generate_session_title_never_raises_on_failure(monkeypatch):
    async def _fake_get_first_user_message_with_content(_db, _session_id):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(
        "app.agent.session_title.get_first_user_message_with_content",
        _fake_get_first_user_message_with_content,
    )

    await generate_session_title(db=object(), session_id="session-1")
