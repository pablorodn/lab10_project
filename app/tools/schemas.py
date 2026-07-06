from typing import Any

from pydantic import BaseModel

from app.tools.catalog import TOOL_CATALOG


class NoArgs(BaseModel):
    """Schema vacío para tools sin argumentos (get_user_preferences, list_enabled_tools)."""


class ReadFileArgs(BaseModel):
    path: str
    offset: int | None = None
    limit: int | None = None


class WriteFileArgs(BaseModel):
    path: str
    content: str


class EditFileArgs(BaseModel):
    path: str
    old_string: str
    new_string: str


class McpExamplePingArgs(BaseModel):
    message: str | None = None


TOOL_ARGS_SCHEMAS: dict[str, type[BaseModel]] = {
    "get_user_preferences": NoArgs,
    "list_enabled_tools": NoArgs,
    "read_file": ReadFileArgs,
    "write_file": WriteFileArgs,
    "edit_file": EditFileArgs,
    "mcp_example_ping": McpExamplePingArgs,
}


def build_tool_schemas(enabled_tool_ids: list[str]) -> list[dict[str, Any]]:
    """Convierte las entradas habilitadas de TOOL_CATALOG en schemas de function-calling
    (formato OpenAI) para bind_tools(). Solo describe nombre/descripción/parámetros;
    la ejecución real sigue pasando por TOOL_HANDLERS en tool_executor_auto_node/
    tool_executor_confirm_node."""
    schemas: list[dict[str, Any]] = []
    for tool in TOOL_CATALOG:
        if tool.id not in enabled_tool_ids:
            continue
        args_model = TOOL_ARGS_SCHEMAS.get(tool.id, NoArgs)
        schemas.append(
            {
                "type": "function",
                "function": {
                    "name": tool.id,
                    "description": tool.description,
                    "parameters": args_model.model_json_schema(),
                },
            }
        )
    return schemas
