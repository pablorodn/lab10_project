#!/usr/bin/env python3
"""Backfill incremental de embeddings semánticos para public.properties.

Standalone (no depende de FastAPI), mismo estilo que scripts/check_connections.py:
credenciales via os.getenv, asyncio.run() en el entrypoint, resumen estructurado por
consola, exit code != 0 si hubo filas fallidas.

Usa PROPERTIES_SUPABASE_URL / PROPERTIES_SUPABASE_SERVICE_ROLE_KEY — nunca la anon key
que usa la app en producción (app/db/properties_client.py). La migración
migrations/properties_db/00003_rls_readonly_anon.sql solo le dio a `anon` SELECT sobre
`properties` y EXECUTE sobre `match_properties`, nada sobre `property_embeddings`; este
script necesita escribir ahí, por eso la credencial de service role (bypasea RLS) es de
uso exclusivo de este proceso offline/manual.

Idempotente: cada fila de property_embeddings guarda el content_hash del documento que
se embebió. Antes de llamar al modelo de embeddings, se recalcula el hash del documento
actual y se compara contra el guardado; si coinciden, se saltea la fila.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, cast

from supabase import AsyncClient, create_async_client

from app.agent.embeddings import generate_embedding

logger = logging.getLogger(__name__)

DESCRIPTION_MAX_CHARS = 600
DEFAULT_BATCH_SIZE = 500
DEFAULT_CONCURRENCY = 5

PROPERTIES_COLUMNS = (
    "id, property_type, operation_type, neighborhood, comuna, bedrooms, "
    "bathrooms, parking_spots, area_m2, stratum, floor_number, description"
)


def _present(value: Any) -> bool:
    if value is None:
        return False
    return not (isinstance(value, str) and not value.strip())


def build_property_document(row: dict[str, Any]) -> str:
    """Documento en texto plano usado para embeber una propiedad.

    Omite con gracia cualquier campo NULL/vacío. Deliberadamente NO incluye
    price_cop/price_usd/admin_fee_cop: esos son filtro estructurado en la RPC, no deben
    influir el ranking semántico.
    """
    intro_parts: list[str] = []
    if _present(row.get("property_type")):
        intro_parts.append(str(row["property_type"]).strip())
    if _present(row.get("operation_type")):
        intro_parts.append(f"en {str(row['operation_type']).strip()}")

    location_bits = [
        str(value).strip()
        for value in (row.get("neighborhood"), row.get("comuna"))
        if _present(value)
    ]
    if location_bits:
        intro_parts.append(f"en {', '.join(location_bits)}, Cali")
    else:
        intro_parts.append("en Cali")

    sentences = [" ".join(intro_parts) + "."]

    attr_bits: list[str] = []
    if _present(row.get("bedrooms")):
        attr_bits.append(f"{row['bedrooms']} habitaciones")
    if _present(row.get("bathrooms")):
        attr_bits.append(f"{row['bathrooms']} baños")
    if _present(row.get("parking_spots")):
        attr_bits.append(f"{row['parking_spots']} parqueadero(s)")
    if _present(row.get("area_m2")):
        attr_bits.append(f"{row['area_m2']} m²")
    if _present(row.get("stratum")):
        attr_bits.append(f"estrato {row['stratum']}")
    if _present(row.get("floor_number")):
        attr_bits.append(f"piso {row['floor_number']}")
    if attr_bits:
        sentences.append(", ".join(attr_bits) + ".")

    description = row.get("description")
    if _present(description):
        truncated = str(description).strip()[:DESCRIPTION_MAX_CHARS].strip()
        if truncated:
            sentences.append(truncated)

    return " ".join(sentences)


def compute_content_hash(document: str) -> str:
    return hashlib.sha256(document.encode("utf-8")).hexdigest()


@dataclass
class BackfillResult:
    scanned: int = 0
    skipped: int = 0
    embedded: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)


async def _iter_active_property_pages(
    client: AsyncClient, batch_size: int, limit: int | None
):
    offset = 0
    fetched_total = 0
    while True:
        page_size = batch_size
        if limit is not None:
            remaining = limit - fetched_total
            if remaining <= 0:
                return
            page_size = min(batch_size, remaining)

        response = await (
            client.table("properties")
            .select(PROPERTIES_COLUMNS)
            .eq("is_active", True)
            .order("id")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        rows = cast("list[dict[str, Any]]", response.data or [])
        if not rows:
            return

        yield rows
        fetched_total += len(rows)
        offset += len(rows)
        if len(rows) < page_size:
            return


async def _fetch_existing_hashes(
    client: AsyncClient, property_ids: list[str]
) -> dict[str, str]:
    if not property_ids:
        return {}
    response = await (
        client.table("property_embeddings")
        .select("property_id, content_hash")
        .in_("property_id", property_ids)
        .execute()
    )
    rows = cast("list[dict[str, Any]]", response.data or [])
    return {row["property_id"]: row["content_hash"] for row in rows}


async def _embed_and_upsert(
    client: AsyncClient,
    semaphore: asyncio.Semaphore,
    property_id: str,
    document: str,
    content_hash: str,
    result: BackfillResult,
) -> None:
    async with semaphore:
        try:
            embedding = await generate_embedding(document)
            await (
                client.table("property_embeddings")
                .upsert(
                    {
                        "property_id": property_id,
                        "embedding": embedding,
                        "content_hash": content_hash,
                        "embedded_at": datetime.now(UTC).isoformat(),
                    },
                    on_conflict="property_id",
                )
                .execute()
            )
            result.embedded += 1
        except Exception as exc:  # pragma: no cover - external service dependent
            logger.warning(
                "No se pudo embeber la propiedad; se continúa con las demás.",
                extra={
                    "event": "property_embedding_failed",
                    "property_id": property_id,
                    "reason": str(exc),
                },
            )
            result.failed.append((property_id, str(exc)))


async def run_backfill(
    client: AsyncClient,
    *,
    batch_size: int,
    concurrency: int,
    limit: int | None,
    dry_run: bool,
) -> BackfillResult:
    result = BackfillResult()
    semaphore = asyncio.Semaphore(concurrency)

    async for page in _iter_active_property_pages(client, batch_size, limit):
        result.scanned += len(page)
        ids = [row["id"] for row in page]
        existing_hashes = await _fetch_existing_hashes(client, ids)

        candidates: list[tuple[str, str, str]] = []
        for row in page:
            document = build_property_document(row)
            current_hash = compute_content_hash(document)
            if existing_hashes.get(row["id"]) == current_hash:
                result.skipped += 1
                continue
            candidates.append((row["id"], document, current_hash))

        if dry_run:
            result.embedded += len(candidates)
            for property_id, _, _ in candidates:
                print(f"[dry-run] embebería: {property_id}")
            continue

        await asyncio.gather(
            *(
                _embed_and_upsert(client, semaphore, property_id, document, content_hash, result)
                for property_id, document, content_hash in candidates
            )
        )

    return result


def _missing_env(keys: list[str]) -> list[str]:
    return [key for key in keys if not os.getenv(key)]


async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill incremental de embeddings semánticos para public.properties."
    )
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    required = ["PROPERTIES_SUPABASE_URL", "PROPERTIES_SUPABASE_SERVICE_ROLE_KEY"]
    missing = _missing_env(required)
    if missing:
        print(f"Faltan variables de entorno: {', '.join(missing)}")
        return 1

    client = await create_async_client(
        os.environ["PROPERTIES_SUPABASE_URL"],
        os.environ["PROPERTIES_SUPABASE_SERVICE_ROLE_KEY"],
    )

    result = await run_backfill(
        client,
        batch_size=args.batch_size,
        concurrency=args.concurrency,
        limit=args.limit,
        dry_run=args.dry_run,
    )

    embedded_label = "Candidatas a embeber (dry-run)" if args.dry_run else "Embebidas (nuevas/actualizadas)"
    print("Backfill de embeddings de propiedades:")
    print(f"- Escaneadas: {result.scanned}")
    print(f"- Sin cambios (skip): {result.skipped}")
    print(f"- {embedded_label}: {result.embedded}")
    print(f"- Fallidas: {len(result.failed)}")
    for property_id, reason in result.failed:
        print(f"  - {property_id}: {reason}")

    if args.dry_run:
        print("\n[dry-run] no se escribió nada.")

    return 1 if result.failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
