from typing import Literal

from pydantic import BaseModel

ToolRisk = Literal["low", "medium", "high"]
# Politica de riesgo (L5): "low" significa "se ejecuta sin confirmacion Y en
# paralelo con otras tools 'low' del mismo batch" (ver asyncio.gather en
# tool_executor_auto_node, app/agent/graph.py). Por eso una tool "low" debe
# ser de solo lectura, o al menos conmutativa/segura bajo ejecucion
# concurrente consigo misma y con otras tools "low" del mismo turno. Un
# patron read-modify-write (ej. incrementar un contador propio) marcado como
# "low" introduce una condicion de carrera real de lost-update que no existe
# hoy porque ninguna tool "low" actual escribe estado compartido. Si una tool
# nueva necesita mutar estado de forma no conmutativa, usar "medium"/"high"
# (requiere confirmacion, se ejecuta sola) en vez de "low".


class ToolDefinition(BaseModel):
    id: str
    name: str
    description: str
    risk: ToolRisk
    display_name: str
    display_description: str


TOOL_CATALOG: list[ToolDefinition] = [
    ToolDefinition(id="get_user_preferences", name="get_user_preferences", description="Get preferences", risk="low", display_name="Preferencias del usuario", display_description="Devuelve configuración actual"),
    ToolDefinition(id="list_enabled_tools", name="list_enabled_tools", description="List enabled tools", risk="low", display_name="Listar herramientas", display_description="Lista herramientas activas"),
    ToolDefinition(id="read_file", name="read_file", description="Read file", risk="low", display_name="Leer archivo", display_description="Lee archivos UTF-8"),
    ToolDefinition(id="write_file", name="write_file", description="Create file", risk="high", display_name="Crear archivo", display_description="Crea archivo nuevo"),
    ToolDefinition(id="edit_file", name="edit_file", description="Edit file", risk="high", display_name="Editar archivo", display_description="Reemplaza una ocurrencia"),
    ToolDefinition(id="mcp_example_ping", name="mcp_example_ping", description="Example MCP-sourced tool (stub)", risk="low", display_name="Ejemplo MCP (ping)", display_description="Tool de referencia del punto de extensión MCP; no se conecta a ningún servidor real"),
    ToolDefinition(
        id="search_properties",
        name="search_properties",
        description=(
            "Busca propiedades reales en venta o arriendo en Cali, Colombia, contra una "
            "base de datos de listados (apartamentos y casas). Usala cuando el usuario "
            "pida buscar, recomendar o comparar propiedades, o pregunte qué hay disponible "
            "según ciertas condiciones.\n\n"
            "Llená los campos estructurados (operation_type, property_type, neighborhood, "
            "comuna, min_bedrooms, min_bathrooms, min_parking, min_price_cop, "
            "max_price_cop, min_area_m2, stratum) SOLO con lo que el usuario mencionó "
            "explícitamente — no inventes ni asumas valores que no dijo (ej. no asumas "
            "un estrato, un mínimo de habitaciones o un rango de precio si no los dio).\n\n"
            "Usá semantic_query únicamente para lo cualitativo o subjetivo que no encaja "
            "en un filtro exacto: amenities, estilo, cercanías, ambiente descrito en "
            "lenguaje natural (ej. 'con balcón, iluminado, cerca de un centro comercial'). "
            "No repitas ahí datos que ya quedaron en los campos estructurados (ej. si el "
            "usuario dijo 'en Pance', eso va en neighborhood, no en semantic_query)."
        ),
        risk="low",
        display_name="Búsqueda de propiedades",
        display_description="Busca propiedades en venta/arriendo en Cali por criterios y lenguaje natural",
    ),
]


def get_tool_definition(tool_id: str) -> ToolDefinition | None:
    return next((tool for tool in TOOL_CATALOG if tool.id == tool_id), None)


def get_tool_risk(tool_id: str) -> ToolRisk:
    tool = get_tool_definition(tool_id)
    return tool.risk if tool else "high"


def tool_requires_confirmation(tool_id: str) -> bool:
    return get_tool_risk(tool_id) in ("medium", "high")


