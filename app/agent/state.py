from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    session_id: str
    user_id: str
    system_prompt: str
    chat_model: str
    compaction_count: int
    compaction_failure_count: int
    compaction_breaker_skips: int
    tool_iteration_count: int
    resolved_confirm_tool_call_ids: list[str]
