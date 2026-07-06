import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.checkpoint.memory import InMemorySaver

import app.agent.graph as graph_module
from app.agent import compaction as compaction_module
from app.agent.compaction import (
    CIRCUIT_BREAKER_LIMIT,
    COMPACTION_TAIL_SIZE,
    llm_compact,
    microcompact,
    should_compact,
)
from app.agent.graph import AgentInput, run_agent
from app.agent.nodes.compaction_node import COMPACTION_BREAKER_RETRY_INTERVAL, compaction_node


def test_should_compact_respects_threshold():
    short = [HumanMessage(content="hola")]
    assert should_compact(short) is False

    big_chars = int(
        compaction_module.CONTEXT_WINDOW_TOKENS
        * compaction_module.COMPACTION_THRESHOLD
        * compaction_module.CHARS_PER_TOKEN
    )
    long_context = [HumanMessage(content="x" * big_chars)]
    assert should_compact(long_context) is True


def test_microcompact_preserves_recent_tail():
    messages = [HumanMessage(content=f"msg-{index}") for index in range(15)]
    compacted = microcompact(messages)

    assert len(compacted) == COMPACTION_TAIL_SIZE
    assert compacted[0].content == "msg-5"
    assert compacted[-1].content == "msg-14"


@pytest.mark.anyio
async def test_llm_compact_preserves_recent_tail(monkeypatch):
    messages = [HumanMessage(content=f"msg-{index}") for index in range(15)]
    llm_calls: list[str] = []

    class _FakeModel:
        async def ainvoke(self, prompt_messages):
            llm_calls.append(str(prompt_messages[0].content))
            return AIMessage(content="## Contexto\nresumen\n## Acciones y herramientas\nninguna")

    monkeypatch.setattr(
        "app.agent.compaction.create_compaction_model",
        lambda: _FakeModel(),
    )

    result = await llm_compact(messages)

    assert len(result) == COMPACTION_TAIL_SIZE + 1
    assert isinstance(result[0], SystemMessage)
    assert "[RESUMEN DE CONTEXTO COMPACTADO]" in str(result[0].content)
    assert "## Contexto" in str(result[0].content)
    assert result[1].content == "msg-5"
    assert result[-1].content == "msg-14"
    assert any("## Contexto" in call for call in llm_calls)


@pytest.mark.anyio
async def test_compaction_node_circuit_breaker_skips_llm_after_limit(monkeypatch):
    messages = [HumanMessage(content=f"msg-{index}") for index in range(15)]
    llm_calls = 0

    async def _fail_llm(_messages):
        nonlocal llm_calls
        llm_calls += 1
        raise RuntimeError("llm unavailable")

    monkeypatch.setattr("app.agent.nodes.compaction_node.should_compact", lambda _messages: True)
    monkeypatch.setattr("app.agent.nodes.compaction_node.llm_compact", _fail_llm)

    state = {
        "messages": messages,
        "compaction_count": 0,
        "compaction_failure_count": CIRCUIT_BREAKER_LIMIT,
        "session_id": "session-1",
    }

    result = await compaction_node(state)

    assert llm_calls == 0
    assert result["compaction_failure_count"] == CIRCUIT_BREAKER_LIMIT
    assert len(result["messages"]) == COMPACTION_TAIL_SIZE + 1
    assert result["messages"][1].content == "msg-5"
    assert result["messages"][-1].content == "msg-14"


@pytest.mark.anyio
async def test_compaction_node_increments_failure_count_before_breaker(monkeypatch):
    messages = [HumanMessage(content=f"msg-{index}") for index in range(15)]
    llm_calls = 0

    async def _fail_llm(_messages):
        nonlocal llm_calls
        llm_calls += 1
        raise RuntimeError("llm unavailable")

    monkeypatch.setattr("app.agent.nodes.compaction_node.should_compact", lambda _messages: True)
    monkeypatch.setattr("app.agent.nodes.compaction_node.llm_compact", _fail_llm)

    state = {
        "messages": messages,
        "compaction_count": 0,
        "compaction_failure_count": 0,
        "session_id": "session-1",
    }

    result = await compaction_node(state)

    assert llm_calls == 1
    assert result["compaction_failure_count"] == 1
    assert result["messages"][-1].content == "msg-14"


@pytest.mark.anyio
async def test_compaction_breaker_half_open_retries_after_interval_and_resets_on_success(
    monkeypatch,
):
    """Circuito abierto (3 fallos) -> N invocaciones de microcompact -> la
    siguiente invocacion vuelve a intentar llm_compact -> si tiene exito,
    compaction_failure_count y compaction_breaker_skips se resetean a 0."""
    messages = [HumanMessage(content=f"msg-{index}") for index in range(15)]
    llm_calls = 0
    llm_should_fail = True

    async def _flaky_llm(_messages):
        nonlocal llm_calls
        llm_calls += 1
        if llm_should_fail:
            raise RuntimeError("llm unavailable")
        return [SystemMessage(content="## Contexto\nresumen"), *_messages[-COMPACTION_TAIL_SIZE:]]

    monkeypatch.setattr("app.agent.nodes.compaction_node.should_compact", lambda _messages: True)
    monkeypatch.setattr("app.agent.nodes.compaction_node.llm_compact", _flaky_llm)

    state: dict = {
        "messages": messages,
        "compaction_count": 0,
        "compaction_failure_count": CIRCUIT_BREAKER_LIMIT,
        "compaction_breaker_skips": 0,
        "session_id": "session-1",
    }

    # Mientras el circuito esta abierto y no se llego al intervalo de retry,
    # cada invocacion toma microcompact sin volver a intentar llm_compact.
    for _ in range(COMPACTION_BREAKER_RETRY_INTERVAL):
        state = {**state, "messages": messages, **(await compaction_node(state))}
    assert llm_calls == 0
    assert state["compaction_breaker_skips"] == COMPACTION_BREAKER_RETRY_INTERVAL
    assert state["compaction_failure_count"] == CIRCUIT_BREAKER_LIMIT

    # Se alcanzo el intervalo: la siguiente invocacion reintenta llm_compact.
    # Si sigue fallando, el intento cuenta pero los skips se reinician (para
    # esperar otro intervalo completo antes del proximo reintento).
    llm_should_fail = True
    state = {**state, "messages": messages, **(await compaction_node(state))}
    assert llm_calls == 1
    assert state["compaction_failure_count"] == CIRCUIT_BREAKER_LIMIT + 1
    assert state["compaction_breaker_skips"] == 0

    # Agotar el intervalo de nuevo y, esta vez, que el reintento tenga exito.
    for _ in range(COMPACTION_BREAKER_RETRY_INTERVAL):
        state = {**state, "messages": messages, **(await compaction_node(state))}
    llm_should_fail = False
    state = {**state, "messages": messages, **(await compaction_node(state))}

    assert llm_calls == 2
    assert state["compaction_failure_count"] == 0
    assert state["compaction_breaker_skips"] == 0


@pytest.mark.anyio
async def test_compaction_breaker_persists_across_separate_run_agent_calls(monkeypatch):
    """Bloque H: regresion contra el reset-por-turno de los contadores de
    compaction. Turno 1 (una sola invocacion de run_agent, con 2 idas y
    vueltas de tools para forzar 3 pasadas de compaction dentro del mismo
    turno) agota el circuit breaker (3 fallos de llm_compact). Turno 2 es una
    invocacion NUEVA de run_agent (no un resume) sobre el mismo session_id: si
    el bug de reset-por-turno siguiera presente, compaction_failure_count
    volveria a 0 y el turno 2 volveria a intentar llm_compact; con el fix
    (aget_state antes de sembrar el input), el contador persistido (3) fluye
    sin resetearse y el turno 2 va directo a microcompact."""
    graph_module._app = None
    try:
        llm_calls = 0

        async def _fake_llm_compact(_messages):
            nonlocal llm_calls
            llm_calls += 1
            raise RuntimeError("compaction model unavailable")

        # should_compact no es async en el codigo real (funcion sincronica),
        # pero compaction_node la llama sin await -- usar un lambda, no una
        # coroutine, para no romper esa firma.
        monkeypatch.setattr(
            "app.agent.nodes.compaction_node.should_compact", lambda _messages: True
        )
        monkeypatch.setattr("app.agent.nodes.compaction_node.llm_compact", _fake_llm_compact)

        async def _fake_memory_injection_node(state, config):
            return {}

        monkeypatch.setattr(graph_module, "memory_injection_node", _fake_memory_injection_node)

        model_calls = 0

        async def _fake_ainvoke_chat_with_fallback(_messages, primary_model=None, tool_schemas=None):
            nonlocal model_calls
            model_calls += 1
            # Dos idas y vueltas de tools (llamadas 1 y 2) para que compaction
            # corra 3 veces en el turno 1: fan-out inicial + 2 loop-backs desde
            # tools_confirm. La llamada 3 responde sin tool_calls y termina el
            # turno. Turno 2 usa una unica llamada final (sin tool_calls).
            if model_calls in (1, 2):
                return AIMessage(
                    content="",
                    tool_calls=[{"id": f"tc-{model_calls}", "name": "get_user_preferences", "args": {}}],
                )
            return AIMessage(content="listo")

        monkeypatch.setattr(
            graph_module, "ainvoke_chat_with_fallback", _fake_ainvoke_chat_with_fallback
        )

        async def _fake_run_with_tracking(**kwargs):
            return await kwargs["handler"](kwargs["args"])

        monkeypatch.setattr(graph_module, "run_with_tracking", _fake_run_with_tracking)

        shared_checkpointer = InMemorySaver()

        async def _fake_get_checkpointer():
            return shared_checkpointer

        monkeypatch.setattr(graph_module, "get_checkpointer", _fake_get_checkpointer)

        turn_1_input = AgentInput(
            user_id="user-1",
            session_id="session-breaker-1",
            system_prompt="Eres un asistente util.",
            db=object(),
            enabled_tools=["get_user_preferences"],
            message="hola",
        )
        await run_agent(turn_1_input)

        # 3 pasadas de compaction en el turno 1 (fan-out + 2 loop-backs), las 3
        # fallando -> circuit breaker agotado (failure_count == CIRCUIT_BREAKER_LIMIT).
        assert llm_calls == CIRCUIT_BREAKER_LIMIT

        app = await graph_module._get_graph_app()
        config = {"configurable": {"thread_id": "session-breaker-1"}}
        snapshot_after_turn_1 = await app.aget_state(config)
        assert snapshot_after_turn_1.values["compaction_failure_count"] == CIRCUIT_BREAKER_LIMIT

        # Turno 2: invocacion NUEVA de run_agent (no resume) sobre el MISMO
        # session_id. Con el bug, el input sembraria compaction_failure_count=0
        # y llm_compact se volveria a llamar (llm_calls pasaria a 4). Con el
        # fix, el breaker sigue abierto y turno 2 va directo a microcompact.
        turn_2_input = AgentInput(
            user_id="user-1",
            session_id="session-breaker-1",
            system_prompt="Eres un asistente util.",
            db=object(),
            enabled_tools=["get_user_preferences"],
            message="segundo mensaje",
        )
        await run_agent(turn_2_input)

        assert llm_calls == CIRCUIT_BREAKER_LIMIT  # no crecio: no se reintento llm_compact
        snapshot_after_turn_2 = await app.aget_state(config)
        assert snapshot_after_turn_2.values["compaction_failure_count"] == CIRCUIT_BREAKER_LIMIT
        assert snapshot_after_turn_2.values["compaction_breaker_skips"] == 1
    finally:
        graph_module._app = None
