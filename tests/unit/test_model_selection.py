import logging

import pytest
from langchain_core.messages import AIMessage

from app.agent import model as model_module
from app.agent.graph import agent_node
from app.agent.model import (
    CURATED_CHAT_MODELS,
    FALLBACK_CHAT_MODEL,
    PRIMARY_CHAT_MODEL,
    ainvoke_chat_with_fallback,
    validate_model_selection,
)


def test_curated_models_are_the_fixed_pair():
    assert CURATED_CHAT_MODELS == ("google/gemini-2.5-flash", "openai/gpt-4o-mini")


@pytest.mark.parametrize("model_name", CURATED_CHAT_MODELS)
def test_validate_model_selection_passes_through_curated_models(model_name):
    assert validate_model_selection(model_name, user_id="user-1") == model_name


def test_validate_model_selection_falls_back_and_warns_on_unknown_model(caplog):
    with caplog.at_level(logging.WARNING, logger="app.agent.model"):
        resolved = validate_model_selection("not-a-real-model", user_id="user-1")
    assert resolved == PRIMARY_CHAT_MODEL
    record = next(r for r in caplog.records if r.message.startswith("Requested chat model"))
    assert record.event == "model_selection_rejected"
    assert record.requested_model == "not-a-real-model"
    assert record.fallback_model == PRIMARY_CHAT_MODEL
    assert record.user_id == "user-1"


def test_validate_model_selection_none_falls_back_silently(caplog):
    with caplog.at_level(logging.WARNING, logger="app.agent.model"):
        resolved = validate_model_selection(None, user_id="user-1")
    assert resolved == PRIMARY_CHAT_MODEL
    assert not any("Requested chat model" in r.message for r in caplog.records)


@pytest.mark.anyio
async def test_ainvoke_chat_with_fallback_propagates_chosen_model_to_create_chat_model(monkeypatch):
    requested_models: list[str] = []

    class _FakeChat:
        async def ainvoke(self, _messages):
            return AIMessage(content="ok")

    def _fake_create_chat_model(model_name: str = PRIMARY_CHAT_MODEL, tool_schemas=None):
        requested_models.append(model_name)
        return _FakeChat()

    monkeypatch.setattr(model_module, "create_chat_model", _fake_create_chat_model)

    result = await ainvoke_chat_with_fallback([], primary_model=FALLBACK_CHAT_MODEL)

    assert result.content == "ok"
    assert requested_models == [FALLBACK_CHAT_MODEL]


@pytest.mark.anyio
async def test_ainvoke_chat_with_fallback_uses_other_curated_model_on_primary_failure(monkeypatch):
    requested_models: list[str] = []

    class _FailingChat:
        async def ainvoke(self, _messages):
            raise RuntimeError("boom")

    class _WorkingChat:
        async def ainvoke(self, _messages):
            return AIMessage(content="fallback-ok")

    def _fake_create_chat_model(model_name: str = PRIMARY_CHAT_MODEL, tool_schemas=None):
        requested_models.append(model_name)
        return _FailingChat() if model_name == FALLBACK_CHAT_MODEL else _WorkingChat()

    monkeypatch.setattr(model_module, "create_chat_model", _fake_create_chat_model)

    result = await ainvoke_chat_with_fallback([], primary_model=FALLBACK_CHAT_MODEL)

    assert result.content == "fallback-ok"
    assert requested_models == [FALLBACK_CHAT_MODEL, PRIMARY_CHAT_MODEL]


@pytest.mark.anyio
async def test_ainvoke_chat_with_fallback_falls_back_when_primary_times_out(monkeypatch, caplog):
    """Bloque A6 (Fase 5): la cobertura de fallback existente (arriba) solo
    usaba un RuntimeError generico. Este test fuerza especificamente un
    TimeoutError en el modelo primario -- el escenario real que
    CHAT_TIMEOUT_SECONDS (app/agent/model.py) esta pensado para acotar -- y
    confirma que el fallback se activa igual que con cualquier otra
    excepcion, con el motivo del timeout en el log."""
    requested_models: list[str] = []

    class _TimingOutChat:
        async def ainvoke(self, _messages):
            raise TimeoutError("Request timed out after 20.0 seconds")

    class _WorkingChat:
        async def ainvoke(self, _messages):
            return AIMessage(content="fallback-ok")

    def _fake_create_chat_model(model_name: str = PRIMARY_CHAT_MODEL, tool_schemas=None):
        requested_models.append(model_name)
        return _TimingOutChat() if model_name == PRIMARY_CHAT_MODEL else _WorkingChat()

    monkeypatch.setattr(model_module, "create_chat_model", _fake_create_chat_model)

    with caplog.at_level(logging.WARNING, logger="app.agent.model"):
        result = await ainvoke_chat_with_fallback([], primary_model=PRIMARY_CHAT_MODEL)

    assert result.content == "fallback-ok"
    assert requested_models == [PRIMARY_CHAT_MODEL, FALLBACK_CHAT_MODEL]
    fallback_records = [
        r for r in caplog.records if r.message == "Primary chat model failed; using fallback."
    ]
    assert fallback_records
    assert "timed out" in fallback_records[0].reason


@pytest.mark.anyio
async def test_ainvoke_chat_with_fallback_propagates_when_fallback_also_times_out(monkeypatch):
    """Documenta un comportamiento real, no necesariamente el deseado: la
    llamada de fallback (a diferencia de la primaria) NO esta envuelta en
    try/except en ainvoke_chat_with_fallback (ver comentario en
    app/agent/model.py). Si el modelo primario Y el de fallback fallan por
    timeout, la excepcion se propaga sin manejar -- no hay un segundo nivel
    de degradacion graceful. Este test prueba ese comportamiento actual tal
    cual existe hoy."""

    class _AlwaysTimingOutChat:
        async def ainvoke(self, _messages):
            raise TimeoutError("Request timed out after 20.0 seconds")

    def _fake_create_chat_model(model_name: str = PRIMARY_CHAT_MODEL, tool_schemas=None):
        return _AlwaysTimingOutChat()

    monkeypatch.setattr(model_module, "create_chat_model", _fake_create_chat_model)

    with pytest.raises(TimeoutError, match="timed out"):
        await ainvoke_chat_with_fallback([], primary_model=PRIMARY_CHAT_MODEL)


@pytest.mark.anyio
async def test_agent_node_propagates_state_chat_model_to_llm_call(monkeypatch):
    captured: dict[str, object] = {}

    async def _fake_ainvoke_chat_with_fallback(
        messages, primary_model=PRIMARY_CHAT_MODEL, tool_schemas=None
    ):
        captured["messages"] = messages
        captured["primary_model"] = primary_model
        return AIMessage(content="respuesta")

    monkeypatch.setattr(
        "app.agent.graph.ainvoke_chat_with_fallback", _fake_ainvoke_chat_with_fallback
    )

    state = {
        "messages": [],
        "system_prompt": "Eres un asistente.",
        "chat_model": FALLBACK_CHAT_MODEL,
    }
    config = {"configurable": {"tool_ctx": {"enabled_tools": []}}}

    result = await agent_node(state, config)

    assert captured["primary_model"] == FALLBACK_CHAT_MODEL
    assert result["messages"][0].content == "respuesta"


@pytest.mark.anyio
async def test_agent_node_defaults_to_primary_model_when_state_missing_chat_model(monkeypatch):
    captured: dict[str, object] = {}

    async def _fake_ainvoke_chat_with_fallback(
        messages, primary_model=PRIMARY_CHAT_MODEL, tool_schemas=None
    ):
        captured["primary_model"] = primary_model
        return AIMessage(content="respuesta")

    monkeypatch.setattr(
        "app.agent.graph.ainvoke_chat_with_fallback", _fake_ainvoke_chat_with_fallback
    )

    state = {"messages": [], "system_prompt": "Eres un asistente."}
    config = {"configurable": {"tool_ctx": {"enabled_tools": []}}}

    await agent_node(state, config)

    assert captured["primary_model"] == PRIMARY_CHAT_MODEL
