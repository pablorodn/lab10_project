import pytest
from langchain_core.messages import HumanMessage

from app.agent.nodes.memory_injection_node import (
    MEMORY_BLOCK_END,
    MEMORY_BLOCK_START,
    _format_memory_block,
    memory_injection_node,
)
from app.db.queries import memories as memories_module


@pytest.mark.anyio
async def test_memory_injection_with_existing_memories(monkeypatch):
    calls: dict[str, object] = {}

    async def _fake_embedding(_text: str):
        return [0.1, 0.2]

    async def _fake_match_memories(_db, user_id, query_embedding, limit=8):
        calls["match"] = {"user_id": user_id, "query_embedding": query_embedding, "limit": limit}
        return [
            {"id": "mem-1", "content": "Prefiere respuestas en español", "type": "episodic"},
            {"id": "mem-2", "content": "Le gusta respuestas breves", "type": "episodic"},
        ]

    async def _fake_increment(_db, memory_ids):
        calls["increment"] = memory_ids

    monkeypatch.setattr("app.agent.nodes.memory_injection_node.generate_embedding", _fake_embedding)
    monkeypatch.setattr("app.agent.nodes.memory_injection_node.match_memories", _fake_match_memories)
    monkeypatch.setattr(
        "app.agent.nodes.memory_injection_node.increment_memory_retrieval_count",
        _fake_increment,
    )

    state = {
        "messages": [HumanMessage(content="¿Qué recuerdas de mí?")],
        "system_prompt": "Eres un asistente útil.",
        "user_id": "user-1",
        "session_id": "session-1",
    }
    config = {"configurable": {"tool_ctx": {"db": object(), "user_id": "user-1"}}}

    result = await memory_injection_node(state, config)

    assert "[MEMORIA DEL USUARIO]" in result["system_prompt"]
    assert "Prefiere respuestas en español" in result["system_prompt"]
    assert "Le gusta respuestas breves" in result["system_prompt"]
    assert result["system_prompt"].endswith("Eres un asistente útil.")
    assert calls["match"] == {"user_id": "user-1", "query_embedding": [0.1, 0.2], "limit": 8}
    assert calls["increment"] == ["mem-1", "mem-2"]


@pytest.mark.anyio
async def test_memory_injection_without_memories(monkeypatch):
    calls: dict[str, object] = {}

    async def _fake_embedding(_text: str):
        return [0.5]

    async def _fake_match_memories(_db, _user_id, _query_embedding, limit=8):
        calls["limit"] = limit
        return []

    async def _fake_increment(_db, memory_ids):
        calls["increment"] = memory_ids

    monkeypatch.setattr("app.agent.nodes.memory_injection_node.generate_embedding", _fake_embedding)
    monkeypatch.setattr("app.agent.nodes.memory_injection_node.match_memories", _fake_match_memories)
    monkeypatch.setattr(
        "app.agent.nodes.memory_injection_node.increment_memory_retrieval_count",
        _fake_increment,
    )

    state = {
        "messages": [HumanMessage(content="hola")],
        "system_prompt": "Prompt base",
        "user_id": "user-1",
        "session_id": "session-1",
    }
    config = {"configurable": {"tool_ctx": {"db": object(), "user_id": "user-1"}}}

    result = await memory_injection_node(state, config)

    assert result["system_prompt"] == "Prompt base"
    assert calls["limit"] == 8
    assert "increment" not in calls


@pytest.mark.anyio
async def test_match_memories_uses_match_user_id_rpc_parameter():
    captured: dict[str, object] = {}

    class _FakeResult:
        data = [{"id": "mem-1", "content": "dato"}]

    class _FakeRpc:
        def __init__(self, name, payload):
            captured["name"] = name
            captured["payload"] = payload

        async def execute(self):
            return _FakeResult()

    class _FakeDb:
        def rpc(self, name, payload):
            return _FakeRpc(name, payload)

    result = await memories_module.match_memories(_FakeDb(), "user-1", [0.1, 0.2], limit=8)

    assert captured["name"] == "match_memories"
    assert captured["payload"] == {
        "query_embedding": [0.1, 0.2],
        "match_user_id": "user-1",
        "match_count": 8,
    }
    assert result == [{"id": "mem-1", "content": "dato"}]


@pytest.mark.anyio
async def test_match_memories_never_returns_another_users_rows():
    """Bloque C3 (Fase 5): la unica cobertura de privacidad existente
    (test_match_memories_uses_match_user_id_rpc_parameter, arriba) solo
    verifica que el cliente Python ENVIA match_user_id en el payload de la
    RPC -- no que el filtrado por usuario realmente aisla los datos. Este
    test emula, en el fake de la RPC, el mismo filtro `WHERE user_id =
    match_user_id` que hace match_memories() en Postgres (definida en
    migrations/00004_long_term_memory.sql), guardando memorias de DOS
    usuarios distintos y verificando que la busqueda de uno nunca devuelve
    filas del otro.

    Limitacion honesta: esto sigue sin ejecutar SQL real -- si el filtro
    `WHERE user_id = match_user_id` se rompiera dentro de la funcion
    Postgres real (y no en el cliente Python), ningun test de este repo lo
    detectaria, porque ninguno corre contra una base real. Lo que este test
    SI detecta es una regresion donde match_memories() (el wrapper Python en
    app/db/queries/memories.py) dejara de mandar el match_user_id correcto
    -- o lo mandara pero el resultado se mezclara indebidamente en el
    camino Python."""

    all_memories = [
        {"id": "mem-a1", "user_id": "user-a", "content": "A prefiere el mate"},
        {"id": "mem-a2", "user_id": "user-a", "content": "A trabaja como ingeniero"},
        {"id": "mem-b1", "user_id": "user-b", "content": "B prefiere el te"},
    ]

    class _FakeResult:
        def __init__(self, data):
            self.data = data

    class _FakeRpc:
        def __init__(self, payload):
            self._payload = payload

        async def execute(self):
            match_user_id = self._payload["match_user_id"]
            filtered = [m for m in all_memories if m["user_id"] == match_user_id]
            return _FakeResult(filtered[: self._payload["match_count"]])

    class _FakeDb:
        def rpc(self, _name, payload):
            return _FakeRpc(payload)

    result_for_a = await memories_module.match_memories(_FakeDb(), "user-a", [0.1, 0.2], limit=8)
    result_for_b = await memories_module.match_memories(_FakeDb(), "user-b", [0.1, 0.2], limit=8)

    assert {m["id"] for m in result_for_a} == {"mem-a1", "mem-a2"}
    assert {m["id"] for m in result_for_b} == {"mem-b1"}
    # La asercion clave anti-fuga: ningun resultado de A tiene el user_id de B
    # y viceversa.
    assert all(m["user_id"] == "user-a" for m in result_for_a)
    assert all(m["user_id"] == "user-b" for m in result_for_b)


def test_format_memory_block_separates_sections_by_type():
    memories = [
        {"id": "mem-1", "content": "Prefiere respuestas en español", "type": "episodic"},
        {"id": "mem-2", "content": "Se llama Pablo y es ingeniero", "type": "semantic"},
        {"id": "mem-3", "content": "Quiere respuestas en listas cortas", "type": "procedural"},
        {"id": "mem-4", "content": "Mensaje sin type reconocido", "type": "unknown"},
        {"id": "mem-5", "content": "Mensaje sin campo type"},
    ]

    block = _format_memory_block(memories)

    assert "[HECHOS Y PREFERENCIAS DEL USUARIO]" in block
    assert "[FORMA DE TRABAJO Y PROCEDIMIENTOS DEL USUARIO]" in block
    assert "[MEMORIA DEL USUARIO]" in block

    semantic_idx = block.index("[HECHOS Y PREFERENCIAS DEL USUARIO]")
    procedural_idx = block.index("[FORMA DE TRABAJO Y PROCEDIMIENTOS DEL USUARIO]")
    episodic_idx = block.index("[MEMORIA DEL USUARIO]")
    assert semantic_idx < procedural_idx < episodic_idx

    assert semantic_idx < block.index("Se llama Pablo y es ingeniero")
    assert procedural_idx < block.index("Quiere respuestas en listas cortas")
    assert episodic_idx < block.index("Prefiere respuestas en español")
    # tipo desconocido y ausente caen en el bucket episodic (mismo principio de
    # robustez que el fallback del clasificador)
    assert episodic_idx < block.index("Mensaje sin type reconocido")
    assert episodic_idx < block.index("Mensaje sin campo type")


def test_format_memory_block_omits_empty_semantic_section():
    memories = [{"id": "mem-1", "content": "Hoy hablamos de viajes", "type": "episodic"}]

    block = _format_memory_block(memories)

    assert "[HECHOS Y PREFERENCIAS DEL USUARIO]" not in block
    assert "[FORMA DE TRABAJO Y PROCEDIMIENTOS DEL USUARIO]" not in block
    assert "[MEMORIA DEL USUARIO]" in block


def test_format_memory_block_omits_empty_episodic_section():
    memories = [{"id": "mem-1", "content": "Se llama Pablo", "type": "semantic"}]

    block = _format_memory_block(memories)

    assert "[MEMORIA DEL USUARIO]" not in block
    assert "[FORMA DE TRABAJO Y PROCEDIMIENTOS DEL USUARIO]" not in block
    assert "[HECHOS Y PREFERENCIAS DEL USUARIO]" in block


def test_format_memory_block_omits_empty_procedural_section():
    memories = [{"id": "mem-1", "content": "Se llama Pablo", "type": "semantic"}]

    block = _format_memory_block(memories)

    assert "[FORMA DE TRABAJO Y PROCEDIMIENTOS DEL USUARIO]" not in block


def test_format_memory_block_wraps_content_with_trust_delimiter():
    memories = [{"id": "mem-1", "content": "Se llama Pablo", "type": "semantic"}]

    block = _format_memory_block(memories)

    assert block.startswith(MEMORY_BLOCK_START)
    assert block.endswith(MEMORY_BLOCK_END)
    start_idx = block.index(MEMORY_BLOCK_START)
    header_idx = block.index("[HECHOS Y PREFERENCIAS DEL USUARIO]")
    end_idx = block.index(MEMORY_BLOCK_END)
    assert start_idx < header_idx < end_idx


def test_format_memory_block_empty_memories_has_no_delimiter():
    block = _format_memory_block([])

    assert block == ""
    assert MEMORY_BLOCK_START not in block
    assert MEMORY_BLOCK_END not in block


def test_format_memory_block_all_blank_content_has_no_delimiter():
    memories = [{"id": "mem-1", "content": "   ", "type": "semantic"}]

    block = _format_memory_block(memories)

    assert block == ""
