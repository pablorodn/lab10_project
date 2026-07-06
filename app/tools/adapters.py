from collections.abc import Awaitable, Callable
from typing import Any

from app.tools.file_tools import execute_edit_file, execute_read_file, execute_write_file
from app.tools.mcp.example_tool import MCP_EXAMPLE_TOOL_ID, handle_mcp_example_ping

ToolHandler = Callable[[dict[str, Any], dict[str, Any]], Awaitable[dict[str, Any]]]


async def handle_get_user_preferences(_: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    return {"preferences": ctx.get("profile", {})}


async def handle_list_enabled_tools(_: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    return {"tools": ctx.get("enabled_tools", [])}


async def handle_read_file(args: dict[str, Any], _: dict[str, Any]) -> dict[str, Any]:
    return {"content": execute_read_file(args["path"], args.get("offset"), args.get("limit"))}


async def handle_write_file(args: dict[str, Any], _: dict[str, Any]) -> dict[str, Any]:
    return {"status": execute_write_file(args["path"], args["content"])}


async def handle_edit_file(args: dict[str, Any], _: dict[str, Any]) -> dict[str, Any]:
    return {"status": execute_edit_file(args["path"], args["old_string"], args["new_string"])}


TOOL_HANDLERS: dict[str, ToolHandler] = {
    "get_user_preferences": handle_get_user_preferences,
    "list_enabled_tools": handle_list_enabled_tools,
    "read_file": handle_read_file,
    "write_file": handle_write_file,
    "edit_file": handle_edit_file,
    MCP_EXAMPLE_TOOL_ID: handle_mcp_example_ping,
}
