"""Tool `search_properties`: búsqueda combinada (semántica + filtros estructurados)
sobre public.properties, un proyecto Supabase separado dedicado a propiedades en
venta/arriendo en Cali (ver migrations/properties_db/). Mismo patrón de subpaquete que
app/tools/mcp/ (ver example_tool.py): un handler async `(args: dict, ctx: dict) -> dict`
registrado en app/tools/adapters.py, sin requerir cambios en app/agent/graph.py.
"""

import logging
from typing import Any, cast

from app.agent.embeddings import generate_embedding
from app.config import get_settings
from app.db.properties_client import create_properties_client

logger = logging.getLogger(__name__)

SEARCH_PROPERTIES_TOOL_ID = "search_properties"


def _present(value: Any) -> bool:
    if value is None:
        return False
    return not (isinstance(value, str) and not value.strip())


def _format_cop(price: int | None) -> str | None:
    """Formatea un monto en COP con separador de miles estilo colombiano (punto).
    Ej. 1200000 -> "1.200.000"."""
    if price is None:
        return None
    return f"{price:,}".replace(",", ".")


def _build_result_line(row: dict[str, Any]) -> str:
    title = row.get("title")
    title_str = str(title).strip() if _present(title) else "Propiedad"

    head = f"**{title_str}**"
    price_cop = row.get("price_cop")
    if price_cop is not None:
        suffix = " /mes" if row.get("operation_type") == "arriendo" else ""
        head += f" — ${_format_cop(int(price_cop))} COP{suffix}"

    attr_bits: list[str] = []
    if _present(row.get("bedrooms")):
        attr_bits.append(f"{row['bedrooms']} hab")
    if _present(row.get("bathrooms")):
        attr_bits.append(f"{row['bathrooms']} baños")
    if _present(row.get("area_m2")):
        attr_bits.append(f"{row['area_m2']} m²")
    if _present(row.get("neighborhood")):
        attr_bits.append(str(row["neighborhood"]).strip())

    parts = [head]
    if attr_bits:
        parts.append(" · ".join(attr_bits))
    sentence = ", ".join(parts) + "."

    listing_url = row.get("listing_url")
    if _present(listing_url):
        # Markdown plano `[texto](url)` — nunca HTML. El render seguro a <a> se hace en
        # un paso posterior separado (front-end); esta tool no debe emitir HTML.
        sentence += f" [Ver publicación]({listing_url})"

    return f"- {sentence}"


async def handle_search_properties(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    if not get_settings().is_properties_db_configured:
        # A diferencia de file_tools.py (que levanta PermissionError cuando
        # FILE_TOOLS_ENABLED está apagado), acá deliberadamente NO levantamos excepción:
        # eso terminaría el turno en el error 502 genérico del router. Preferimos que el
        # modelo reciba este dict de error y pueda explicarle la situación al usuario
        # dentro del mismo turno.
        return {
            "error": "not_configured",
            "message": "La búsqueda de propiedades no está configurada actualmente.",
        }

    try:
        semantic_query = (args.get("semantic_query") or "").strip()
        query_embedding = await generate_embedding(semantic_query) if semantic_query else None

        # Mapeo explícito de los argumentos "amigables" del schema a los nombres p_* de
        # match_properties (migrations/properties_db/00002_match_properties_rpc.sql) —
        # no asumir que coinciden.
        params = {
            "query_embedding": query_embedding,
            "p_operation_type": args.get("operation_type"),
            "p_property_type": args.get("property_type"),
            "p_neighborhood": args.get("neighborhood"),
            "p_comuna": args.get("comuna"),
            "p_min_bedrooms": args.get("min_bedrooms"),
            "p_min_bathrooms": args.get("min_bathrooms"),
            "p_min_parking": args.get("min_parking"),
            "p_min_price_cop": args.get("min_price_cop"),
            "p_max_price_cop": args.get("max_price_cop"),
            "p_min_area_m2": args.get("min_area_m2"),
            "p_stratum": args.get("stratum"),
            "match_count": args.get("limit", 8),
        }

        db = await create_properties_client()
        response = await db.rpc("match_properties", params).execute()
    except Exception as exc:  # pragma: no cover - external service dependent
        logger.warning(
            "No se pudo completar la búsqueda de propiedades.",
            extra={"event": "property_search_error", "reason": str(exc)},
        )
        return {
            "error": "search_failed",
            "message": "No pude completar la búsqueda de propiedades en este momento.",
        }

    results = cast("list[dict[str, Any]]", response.data or [])
    if not results:
        return {
            "results": [],
            "count": 0,
            "formatted_markdown": "",
            "message": "No encontré propiedades que coincidan con esos criterios. "
            "Podrías intentar con filtros más amplios.",
        }

    return {
        "results": results,
        "count": len(results),
        "formatted_markdown": "\n".join(_build_result_line(row) for row in results),
    }
