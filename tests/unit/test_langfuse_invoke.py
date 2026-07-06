import pytest

from app.agent.langfuse import augment_invoke_config, build_langfuse_tags


def test_build_langfuse_tags_for_message():
    assert build_langfuse_tags(is_resume=False) == ["agent_total", "interactive", "message"]


def test_build_langfuse_tags_for_resume():
    assert build_langfuse_tags(is_resume=True) == ["agent_total", "interactive", "resume"]


def test_augment_invoke_config_attaches_callback_when_keys_present(monkeypatch):
    class _FakeHandler:
        pass

    monkeypatch.setattr("app.agent.langfuse.create_langfuse_callback", lambda: _FakeHandler())

    config = augment_invoke_config(
        {"configurable": {"thread_id": "session-1"}},
        user_id="user-1",
        session_id="session-1",
        is_resume=False,
    )

    assert len(config["callbacks"]) == 1
    assert isinstance(config["callbacks"][0], _FakeHandler)
    assert config["metadata"]["langfuse_user_id"] == "user-1"
    assert config["metadata"]["langfuse_session_id"] == "session-1"
    assert config["metadata"]["langfuse_tags"] == ["agent_total", "interactive", "message"]
    assert config["configurable"]["thread_id"] == "session-1"


def test_augment_invoke_config_uses_resume_tag(monkeypatch):
    monkeypatch.setattr("app.agent.langfuse.create_langfuse_callback", lambda: object())

    config = augment_invoke_config(
        {"configurable": {"thread_id": "session-1"}},
        user_id="user-1",
        session_id="session-1",
        is_resume=True,
    )

    assert config["metadata"]["langfuse_tags"] == ["agent_total", "interactive", "resume"]


def test_augment_invoke_config_stable_without_keys(monkeypatch):
    monkeypatch.setattr("app.agent.langfuse.create_langfuse_callback", lambda: None)

    config = augment_invoke_config(
        {"configurable": {"thread_id": "session-1", "tool_ctx": {"db": object()}}},
        user_id="user-1",
        session_id="session-1",
        is_resume=False,
    )

    assert "callbacks" not in config
    assert config["metadata"]["langfuse_user_id"] == "user-1"
    assert config["metadata"]["langfuse_session_id"] == "session-1"
    assert config["metadata"]["langfuse_tags"] == ["agent_total", "interactive", "message"]
    assert config["configurable"]["tool_ctx"]["db"] is not None


@pytest.mark.anyio
async def test_run_agent_passes_langfuse_config_on_message(monkeypatch):
    from langchain_core.messages import AIMessage

    from app.agent.graph import AgentInput, run_agent

    captured: dict[str, object] = {}

    class _FakeSnapshot:
        values: dict = {}

    class _FakeApp:
        async def aget_state(self, config=None):
            return _FakeSnapshot()

        async def ainvoke(self, _payload, config=None):
            captured["config"] = config
            return {"messages": [AIMessage(content="ok")]}

    async def _fake_get_graph_app():
        return _FakeApp()

    class _FakeHandler:
        pass

    monkeypatch.setattr("app.agent.graph._get_graph_app", _fake_get_graph_app)
    monkeypatch.setattr("app.agent.langfuse.create_langfuse_callback", lambda: _FakeHandler())

    await run_agent(
        AgentInput(
            user_id="user-1",
            session_id="session-1",
            system_prompt="prompt",
            db=object(),  # type: ignore[arg-type]
            enabled_tools=[],
            message="hola",
        )
    )

    config = captured["config"]
    assert isinstance(config, dict)
    assert len(config["callbacks"]) == 1  # type: ignore[index]
    assert config["metadata"]["langfuse_tags"] == ["agent_total", "interactive", "message"]  # type: ignore[index]


@pytest.mark.anyio
async def test_run_agent_uses_resume_tag_for_hitl_resume(monkeypatch):
    from langchain_core.messages import AIMessage
    from langgraph.types import Command

    from app.agent.graph import AgentInput, run_agent

    captured: dict[str, object] = {}

    class _FakeApp:
        async def ainvoke(self, payload, config=None):
            captured["payload"] = payload
            captured["config"] = config
            return {"messages": [AIMessage(content="ok")]}

    async def _fake_get_graph_app():
        return _FakeApp()

    monkeypatch.setattr("app.agent.graph._get_graph_app", _fake_get_graph_app)
    monkeypatch.setattr("app.agent.langfuse.create_langfuse_callback", lambda: None)

    await run_agent(
        AgentInput(
            user_id="user-1",
            session_id="session-1",
            system_prompt="prompt",
            db=object(),  # type: ignore[arg-type]
            enabled_tools=[],
            resume_decision="approve",
        )
    )

    assert isinstance(captured["payload"], Command)
    config = captured["config"]
    assert isinstance(config, dict)
    assert "callbacks" not in config
    assert config["metadata"]["langfuse_tags"] == ["agent_total", "interactive", "resume"]  # type: ignore[index]
