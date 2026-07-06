"""Scaffolding de referencia para registrar una tool proveniente de un servidor MCP.

Este módulo NO se conecta a ningún servidor MCP real y no depende de ningún SDK
MCP (`mcp`, `langchain-mcp-adapters`, etc.). Demuestra únicamente el contrato
que debe cumplir el handler de una tool MCP real -- firma async
`(args: dict, ctx: dict) -> dict`, igual que cualquier handler en
`app/tools/adapters.py` -- para poder registrarse por el mismo mecanismo que
el resto del catálogo (`app/tools/catalog.py` + `app/tools/adapters.py`), sin
requerir cambios en `app/agent/graph.py`.

Ver `docs/mcp-extension-example.md` para la guía completa de cómo reemplazar
este stub por una integración MCP real.
"""

from typing import Any

from app.config import get_settings

MCP_EXAMPLE_TOOL_ID = "mcp_example_ping"


async def handle_mcp_example_ping(args: dict[str, Any], _: dict[str, Any]) -> dict[str, Any]:
    # En una integración MCP real, este handler abriría un cliente MCP (por
    # ejemplo vía el SDK `mcp`, sobre transporte stdio o HTTP) apuntando a
    # `MCP_EXAMPLE_SERVER_URL` e invocaría la tool remota correspondiente,
    # devolviendo su resultado. Aquí se simula la respuesta para poder
    # demostrar el contrato de registro sin depender de un servidor externo.
    server_url = get_settings().mcp_example_server_url
    message = args.get("message", "")
    return {"pong": True, "echo": message, "would_call_server": server_url}
