import pytest

from app.agent.memory_flush import flush_session_memory
from app.db.queries.messages import AgentMessage
from app.services.memory_policy import can_store_memory


def test_memory_policy_blocks_sensitive_text():
    assert can_store_memory("my token is 123") is False


def test_memory_policy_allows_regular_text():
    assert can_store_memory("I prefer replies in Spanish") is True


@pytest.mark.anyio
async def test_flush_session_memory_blocks_sensitive_content(monkeypatch):
    calls: dict[str, object] = {}

    async def _fake_last_message(_db, _session_id):
        return AgentMessage(
            id="msg-1", session_id="session-1", role="user", content="my password is secret123"
        )

    async def _fake_embedding(_text):
        calls["embedding"] = _text
        return [0.1]

    async def _fake_save_memory(_db, **kwargs):
        calls["save"] = kwargs

    monkeypatch.setattr("app.agent.memory_flush.get_last_user_message", _fake_last_message)
    monkeypatch.setattr("app.agent.memory_flush.generate_embedding", _fake_embedding)
    monkeypatch.setattr("app.agent.memory_flush.save_memory", _fake_save_memory)

    await flush_session_memory(db=object(), user_id="user-1", session_id="session-1")

    assert "embedding" not in calls
    assert "save" not in calls


@pytest.mark.anyio
async def test_flush_session_memory_handles_external_errors(monkeypatch):
    async def _fake_last_message(_db, _session_id):
        return AgentMessage(id="msg-1", session_id="session-1", role="user", content="hola")

    async def _broken_embedding(_text):
        raise RuntimeError("embedding down")

    monkeypatch.setattr("app.agent.memory_flush.get_last_user_message", _fake_last_message)
    monkeypatch.setattr("app.agent.memory_flush.generate_embedding", _broken_embedding)

    await flush_session_memory(db=object(), user_id="user-1", session_id="session-1")


@pytest.mark.anyio
async def test_flush_session_memory_persists_user_content_not_assistant(monkeypatch):
    calls: dict[str, object] = {}

    async def _fake_last_message(_db, _session_id):
        # get_last_user_message ya filtra por role="user" a nivel SQL: un
        # mensaje de assistant nunca llega a ser el resultado de esta función.
        return AgentMessage(id="msg-1", session_id="session-1", role="user", content="mensaje del usuario")

    async def _fake_embedding(_text):
        calls["embedding"] = _text
        return [0.1]

    async def _fake_save_memory(_db, **kwargs):
        calls["save"] = kwargs

    monkeypatch.setattr("app.agent.memory_flush.get_last_user_message", _fake_last_message)
    monkeypatch.setattr("app.agent.memory_flush.generate_embedding", _fake_embedding)
    monkeypatch.setattr("app.agent.memory_flush.save_memory", _fake_save_memory)

    await flush_session_memory(db=object(), user_id="user-1", session_id="session-1")

    assert calls["embedding"] == "mensaje del usuario"
    assert calls["save"]["content"] == "mensaje del usuario"
