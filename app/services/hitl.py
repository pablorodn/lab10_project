from typing import Any

from app.tools.catalog import get_tool_risk


def sanitize_args(_: str, args: dict[str, Any]) -> dict[str, Any]:
    redacted_keys = {"token", "secret", "password", "authorization"}
    out: dict[str, Any] = {}
    for key, value in args.items():
        if key.lower() in redacted_keys:
            out[key] = "***"
        else:
            out[key] = value
    return out


def build_confirmation_message(tool_id: str, args: dict[str, Any]) -> str:
    risk = get_tool_risk(tool_id)
    return f"¿Confirmas ejecutar '{tool_id}' (riesgo {risk}) con argumentos {sanitize_args(tool_id, args)}?"
