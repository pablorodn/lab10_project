import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.agent.graph import AgentInput, _build_initial_messages, run_agent


def test_build_initial_messages_text_only_keeps_plain_string_content():
    messages = _build_initial_messages("hola", None)

    assert len(messages) == 1
    assert isinstance(messages[0], HumanMessage)
    assert messages[0].content == "hola"


def test_build_initial_messages_attachments_only_omits_text_block():
    blocks = [{"type": "image", "base64": "abc", "mime_type": "image/png"}]

    messages = _build_initial_messages("", blocks)

    assert len(messages) == 1
    assert messages[0].content == blocks


def test_build_initial_messages_text_and_attachments_combines_blocks():
    blocks = [{"type": "image", "base64": "abc", "mime_type": "image/jpeg"}]

    messages = _build_initial_messages("revisa esto", blocks)

    assert messages[0].content[0] == {"type": "text", "text": "revisa esto"}
    assert messages[0].content[1] == blocks[0]


def test_build_initial_messages_empty_everything_returns_no_messages():
    assert _build_initial_messages("", None) == []
    assert _build_initial_messages(None, None) == []


@pytest.mark.anyio
async def test_run_agent_passes_multimodal_content_to_graph(monkeypatch):
    captured: dict[str, object] = {}

    class _FakeSnapshot:
        values: dict = {}

    class _FakeApp:
        async def aget_state(self, config=None):
            return _FakeSnapshot()

        async def ainvoke(self, payload, config=None):
            captured["payload"] = payload
            return {"messages": [AIMessage(content="ok")]}

    async def _fake_get_graph_app():
        return _FakeApp()

    monkeypatch.setattr("app.agent.graph._get_graph_app", _fake_get_graph_app)
    monkeypatch.setattr("app.agent.langfuse.create_langfuse_callback", lambda: None)

    image_block = {"type": "image", "base64": "abc", "mime_type": "image/png"}
    await run_agent(
        AgentInput(
            user_id="user-1",
            session_id="session-1",
            system_prompt="prompt",
            db=object(),  # type: ignore[arg-type]
            enabled_tools=[],
            message="mira esta imagen",
            attachment_blocks=[image_block],
        )
    )

    payload = captured["payload"]
    assert isinstance(payload, dict)
    sent_messages = payload["messages"]
    assert len(sent_messages) == 1
    assert sent_messages[0].content == [
        {"type": "text", "text": "mira esta imagen"},
        image_block,
    ]
