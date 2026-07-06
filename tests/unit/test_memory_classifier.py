from types import SimpleNamespace

import pytest

from app.agent.memory_classifier import classify_memory_type


class _FakeModel:
    def __init__(self, content):
        self._content = content
        self.received_messages = None

    async def ainvoke(self, messages):
        self.received_messages = messages
        return SimpleNamespace(content=self._content)


@pytest.mark.anyio
async def test_classify_memory_type_returns_semantic(monkeypatch):
    fake_model = _FakeModel("semantic")
    monkeypatch.setattr("app.agent.memory_classifier.create_compaction_model", lambda: fake_model)

    result = await classify_memory_type("Me llamo Pablo y soy ingeniero")

    assert result == "semantic"


@pytest.mark.anyio
async def test_classify_memory_type_returns_procedural(monkeypatch):
    fake_model = _FakeModel("procedural")
    monkeypatch.setattr("app.agent.memory_classifier.create_compaction_model", lambda: fake_model)

    result = await classify_memory_type("Prefiero que me respondas con listas cortas y sin rodeos")

    assert result == "procedural"


@pytest.mark.anyio
async def test_classify_memory_type_returns_episodic(monkeypatch):
    fake_model = _FakeModel("  Episodic  ")
    monkeypatch.setattr("app.agent.memory_classifier.create_compaction_model", lambda: fake_model)

    result = await classify_memory_type("Hoy tuve una reunion complicada")

    assert result == "episodic"


@pytest.mark.anyio
async def test_classify_memory_type_defaults_to_episodic_on_ambiguous_response(monkeypatch):
    fake_model = _FakeModel("no estoy seguro")
    monkeypatch.setattr("app.agent.memory_classifier.create_compaction_model", lambda: fake_model)

    result = await classify_memory_type("contenido cualquiera")

    assert result == "episodic"


@pytest.mark.anyio
async def test_classify_memory_type_defaults_to_episodic_on_error(monkeypatch):
    def _raise():
        raise RuntimeError("model unavailable")

    monkeypatch.setattr("app.agent.memory_classifier.create_compaction_model", _raise)

    result = await classify_memory_type("contenido cualquiera")

    assert result == "episodic"
