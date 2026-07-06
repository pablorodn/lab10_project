# Guía de extensión de agent_total

Este documento es el procedimiento para agregar una integración nueva a `agent_total` (una
tool nueva, una integración MCP, etc.) sobre el mecanismo de catálogo + adapter ya existente.
Invoca directamente las reglas ya declaradas en `.cursor/.rules/` — no las repite.

## Reglas que gobiernan el procedimiento

- **Arquitectura e invariantes** (grafo canónico, capas, fuentes de verdad):
  `.cursor/.rules/architecture.mdc`.
- **Guardrails de calidad e implementación** (qué no romper, qué no modificar sin
  autorización): `.cursor/.rules/guardrails.mdc`.
- **Seguridad** (HITL obligatorio, fail-closed, confinamiento de filesystem):
  `.cursor/.rules/security.mdc`.
- **Testing** (matriz mínima por área funcional, qué probar antes de cerrar un cambio):
  `.cursor/.rules/testing.mdc`.
- **Cómo colaborar implementando** (documentación como fuente de verdad, qué hacer ante
  ambigüedad): `.cursor/.rules/implementation-agent.mdc`.

## Mecanismo genérico de extensión

Los nodos de ejecución de tools (`tool_executor_auto_node`/`tool_executor_confirm_node` en
`app/agent/graph.py`) no conocen nombres de tools: resuelven todo a través de dos puntos de
extensión únicos —

1. `app/tools/catalog.py` (`TOOL_CATALOG`): metadatos (id, `risk`, textos de UI).
2. `app/tools/adapters.py` (`TOOL_HANDLERS`): el handler que ejecuta la tool.

El nivel de `risk` determina si la tool pausa por HITL (`medium`/`high`, regla de
`security.mdc`) o se ejecuta directo con tracking (`low`). Agregar una tool nueva es agregar
una entrada en cada uno de esos dos archivos; `app/agent/graph.py` queda con diff cero. Ver
`docs/implementation-summary.md` para el detalle del mecanismo y `docs/mcp-extension-example.md`
para un stub de referencia ya implementado (`mcp_example_ping`).

## Procedimiento para implementar una integración nueva

1. **Definir el contrato**: `ToolDefinition` en el catálogo (id, `risk`, textos de UI) y el
   schema de argumentos (Pydantic, `app/tools/schemas.py`).
2. **Declarar el `risk`** según el impacto real (`security.mdc`): `low` si es de solo lectura
   y sin efectos secundarios sensibles; `medium`/`high` si escribe, ejecuta acciones externas,
   o expone datos que ameritan confirmación humana.
3. **Implementar el handler** en `TOOL_HANDLERS` con el contrato `(args: dict, ctx: dict) ->
   dict`. El `ctx` (`tool_ctx`) trae `db`, `user_id`, `session_id`, `enabled_tools`.
4. **Configuración**: si la integración necesita URL/credenciales, agregarlas a
   `app/config.py` (`Settings`) y a `.env.example`, siguiendo el patrón de
   `MCP_EXAMPLE_SERVER_URL` u `OPENROUTER_API_KEY`.
5. **Migraciones**: si hace falta una tabla nueva, agregar una migración incremental en
   `migrations/`; nunca modificar una ya mergeada (`guardrails.mdc`).
6. **Tests** (`testing.mdc`): unitarios para el handler y el schema; integración para el
   flujo completo vía `tool_executor_auto_node`/`tool_executor_confirm_node` (mismo patrón que
   `tests/unit/test_mcp_extension.py`).
7. **Cierre**: `ruff check .`, `mypy app/`, `pytest -q` en verde
   (`implementation-agent.mdc`). Si se tocó documentación, confirmar que no quedaron
   referencias a código/rutas/tools que ya no existen.

## Ejemplo de diseño: tool MCP contra una base de datos externa

Caso de uso: el usuario pregunta algo en lenguaje natural en el chat (ej. "¿cuántos pedidos
tuvo el cliente X el mes pasado?"), y la tool debe traducir eso en una consulta contra una
base de datos externa (vía un servidor MCP que expone esa base) y devolver una respuesta que
el modelo pueda convertir de nuevo a lenguaje natural.

Diseño a nivel de contrato (aplicando el procedimiento de arriba, sin código todavía):

- **Catálogo**: entrada nueva, por ejemplo `id="query_external_db"`. `risk` a definir según el
  caso — `low` si es de solo-lectura contra una base que no expone datos sensibles de otros
  usuarios; `medium`/`high` si puede exponer datos que ameriten confirmación, o si la base
  permite escritura.
- **Schema de argumentos**: típicamente `{"question": str}` (la pregunta en lenguaje natural),
  o los parámetros que espere el servidor MCP si ya expone una query estructurada. Evitar
  aceptar SQL crudo desde el modelo directamente; preferir que el servidor MCP (o una capa
  intermedia) traduzca la pregunta a una consulta acotada y parametrizada.
- **Handler**: abre una sesión con el servidor MCP configurado (patrón de
  `MCP_EXAMPLE_SERVER_URL` para la URL/config de conexión), ejecuta la consulta, y devuelve un
  resultado ya resumido/estructurado — el `ToolMessage` que ve el modelo es el resultado de la
  tool, no la respuesta final al usuario.
- **Seguridad** (`security.mdc`): fail-closed si no está en `enabled_tools`, HITL si el `risk`
  declarado lo amerita, y ownership/scoping de qué datos externos puede ver cada usuario (si
  la base externa es multi-tenant, la tool debe filtrar por el usuario/tenant correspondiente
  antes de devolver resultados, no confiar en que el modelo pida solo lo suyo).
- **Reemplazar el stub por la integración real**: seguir los 4 pasos de
  `docs/mcp-extension-example.md` ("Cómo reemplazar el stub por una integración MCP real"),
  usando el cliente MCP elegido (SDK oficial `mcp`, o `langchain-mcp-adapters`) para abrir la
  sesión contra el servidor que expone la base de datos externa.
