from typing import Any, Literal

from pydantic import BaseModel, Field

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


class SearchPropertiesArgs(BaseModel):
    # operation_type/property_type: los únicos dos valores reales hoy en cada columna
    # (ver migrations/properties_db/). Si el dataset agrega categorías nuevas (ej.
    # "oficina", "lote") este Literal necesita actualizarse a mano — limitación conocida,
    # deliberada: preferible fallar explícito/acotado a aceptar cualquier string que
    # después no matchea nada en match_properties().
    operation_type: Literal["venta", "arriendo"] | None = None
    property_type: Literal["apartamento", "casa"] | None = None
    neighborhood: str | None = Field(
        default=None,
        description="Nombre de barrio o zona, en lenguaje natural (match "
        "parcial, no sensible a mayúsculas) — ej. 'pance', 'el ingenio'.",
    )
    comuna: str | None = None
    min_bedrooms: int | None = None
    min_bathrooms: int | None = None
    min_parking: int | None = None
    min_price_cop: int | None = None
    max_price_cop: int | None = None
    min_area_m2: float | None = None
    stratum: int | None = None
    semantic_query: str | None = Field(
        default=None,
        description="Aspectos cualitativos/subjetivos de la búsqueda que "
        "NO son un filtro exacto: amenities, estilo, cercanías, "
        "características descritas en lenguaje natural (ej. 'con balcón, "
        "iluminado, cerca de un centro comercial'). No repitas acá "
        "filtros que ya llenaste en los demás campos.",
    )
    limit: int = Field(default=8, ge=1, le=15)


TOOL_ARGS_SCHEMAS: dict[str, type[BaseModel]] = {
    "get_user_preferences": NoArgs,
    "list_enabled_tools": NoArgs,
    "read_file": ReadFileArgs,
    "write_file": WriteFileArgs,
    "edit_file": EditFileArgs,
    "mcp_example_ping": McpExamplePingArgs,
    "search_properties": SearchPropertiesArgs,
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
