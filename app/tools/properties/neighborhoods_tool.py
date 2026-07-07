"""Tool `list_neighborhoods`: descubrimiento de barrios por filtros,
sin devolver propiedades individuales. Mismo patrón que search_tool.py."""

import logging
from typing import Any, cast

from app.config import get_settings
from app.db.properties_client import create_properties_client

logger = logging.getLogger(__name__)

LIST_NEIGHBORHOODS_TOOL_ID = "list_neighborhoods"


def _format_cop(price: int | None) -> str | None:
    """Mismo formato que search_tool.py."""
    if price is None:
        return None
    return f"{price:,}".replace(",", ".")


def _build_neighborhood_line(row: dict[str, Any]) -> str:
    """Formatea un resultado de neighborhood.

    Ejemplo: "- **El Ingenio** — 4 opciones desde $1.800.000 COP"
    """
    neighborhood = str(row.get("neighborhood", "")).strip() or "Zona desconocida"
    count = row.get("property_count", 0)
    min_price = row.get("min_price_cop")

    line = f"- **{neighborhood}**"

    # Plural/singular
    option_word = "opción" if count == 1 else "opciones"
    line += f" — {count} {option_word}"

    if min_price is not None:
        price_str = _format_cop(int(min_price))
        line += f" desde ${price_str} COP"

    line += "."
    return line


async def handle_list_neighborhoods(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    if not get_settings().is_properties_db_configured:
        return {
            "error": "not_configured",
            "message": "La búsqueda de propiedades no está configurada actualmente.",
        }

    try:
        # Mapeo explícito (mismo patrón que search_tool.py, sin neighborhood/comuna/embedding)
        params = {
            "p_operation_type": args.get("operation_type"),
            "p_property_type": args.get("property_type"),
            "p_min_bedrooms": args.get("min_bedrooms"),
            "p_min_bathrooms": args.get("min_bathrooms"),
            "p_min_parking": args.get("min_parking"),
            "p_min_price_cop": args.get("min_price_cop"),
            "p_max_price_cop": args.get("max_price_cop"),
            "p_min_area_m2": args.get("min_area_m2"),
            "p_stratum": args.get("stratum"),
            "p_limit": args.get("limit", 20),
        }

        db = await create_properties_client()
        response = await db.rpc("neighborhoods_by_filters", params).execute()
    except Exception as exc:  # pragma: no cover - external service dependent
        logger.warning(
            "No se pudo completar la búsqueda de barrios.",
            extra={"event": "neighborhoods_search_error", "reason": str(exc)},
        )
        return {
            "error": "search_failed",
            "message": "No pude completar la búsqueda de barrios en este momento.",
        }

    results = cast("list[dict[str, Any]]", response.data or [])
    if not results:
        return {
            "results": [],
            "count": 0,
            "formatted_markdown": "",
            "message": "No encontré barrios que coincidan con esos criterios.",
        }

    return {
        "results": results,
        "count": len(results),
        "formatted_markdown": "\n".join(_build_neighborhood_line(row) for row in results),
    }
