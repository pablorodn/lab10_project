# Ejemplo de referencia: registrar una tool de servidor MCP

Este documento muestra, con un ejemplo concreto y ejecutable, cómo `agent_total` permite
registrar una tool nueva -- incluyendo una proveniente de un servidor MCP --
sin modificar `app/agent/graph.py`. Ver `docs/extending.md` para el checklist general de
extensión y un ejemplo de diseño más cercano a un caso real (tool MCP contra una base de
datos externa).

## Qué es y qué no es este ejemplo

- **Es** un scaffolding mínimo: demuestra el contrato y el mecanismo de
  registro (catálogo + adapter) que debería seguir cualquier tool MCP real.
- **No** se conecta a ningún servidor MCP real y **no** agrega ninguna
  dependencia nueva (`mcp`, `langchain-mcp-adapters`, etc.) al proyecto. El
  handler de ejemplo simula la respuesta que devolvería un cliente MCP real.

## Mecanismo genérico ya existente

`app/agent/graph.py` no conoce los nombres de las tools: los nodos de ejecución
(`tool_executor_auto_node`/`tool_executor_confirm_node`) resuelven el handler a
ejecutar consultando dos únicos puntos de extensión:

1. `app/tools/catalog.py` -- `TOOL_CATALOG` (metadatos: id, riesgo,
   textos de UI) y `TOOL_HANDLERS` en `app/tools/adapters.py` (ejecución).
2. El nivel de riesgo (`get_tool_risk`) determina si la tool requiere
   confirmación HITL (`medium`/`high`) o se ejecuta directo vía
   `run_with_tracking` (`low`), pero esa rama ya es genérica y no depende del
   nombre de la tool.

Registrar una tool nueva -- MCP o no -- consiste en agregar entradas a esos
dos archivos; `graph.py` queda intacto.

## Archivos de este ejemplo

- `app/tools/mcp/example_tool.py`: handler `handle_mcp_example_ping` y
  constante `MCP_EXAMPLE_TOOL_ID = "mcp_example_ping"`.
- `app/tools/catalog.py`: entrada `ToolDefinition(id="mcp_example_ping", ...)`
  con `risk="low"`, añadida al final de `TOOL_CATALOG`.
- `app/tools/adapters.py`: import de `handle_mcp_example_ping` y registro en
  `TOOL_HANDLERS[MCP_EXAMPLE_TOOL_ID]`.
- `app/config.py` / `.env.example`: `MCP_EXAMPLE_SERVER_URL` (opcional,
  ilustrativa) -- muestra el patrón de configuración que tendría una
  integración MCP real futura (URL/endpoint del servidor), aunque el stub
  actual no llega a conectarse a ella.
- `tests/unit/test_mcp_extension.py`: verifica que la tool queda registrada
  en el catálogo y que se ejecuta correctamente a través de
  `tool_executor_auto_node` (importado sin cambios desde `app.agent.graph`),
  exactamente igual que cualquier otra tool `low`.

## Cómo reemplazar el stub por una integración MCP real

1. Agregar la dependencia del cliente MCP elegido (por ejemplo el SDK
   oficial `mcp`, o `langchain-mcp-adapters`) a `pyproject.toml`.
2. Sustituir el cuerpo de `handle_mcp_example_ping` (o crear un handler
   nuevo con el mismo contrato `(args: dict, ctx: dict) -> dict`) para que
   abra una sesión con el servidor MCP real (usando `MCP_EXAMPLE_SERVER_URL`
   u otra variable de configuración) e invoque la tool remota.
3. Ajustar `risk` en `catalog.py` según el impacto real de la tool remota
   (una tool MCP que escribe o ejecuta acciones externas normalmente debería
   ser `medium` o `high`, no `low`).
4. No es necesario tocar `app/agent/graph.py` en ningún paso de este proceso.

## Cómo probarlo manualmente

1. Habilitar `mcp_example_ping` para un usuario desde `/settings` (aparece
   en la lista de tools igual que `read_file`/`write_file`).
2. Iniciar una conversación donde el modelo decida invocar la tool
   `mcp_example_ping` (o invocar `tool_executor_auto_node` directamente, como
   hace `tests/unit/test_mcp_extension.py`).
3. La respuesta será un JSON `{"pong": true, "echo": "<mensaje>",
   "would_call_server": "<MCP_EXAMPLE_SERVER_URL o null>"}`.
