#!/usr/bin/env python3
"""Connectivity checks for Phase 2 (local, non-destructive)."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import asyncpg
import httpx


@dataclass
class CheckResult:
    name: str
    ok: bool
    message: str


def _missing(keys: list[str]) -> list[str]:
    return [k for k in keys if not os.getenv(k)]


async def check_supabase_rest() -> CheckResult:
    required = ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"]
    missing = _missing(required)
    if missing:
        return CheckResult(
            name="supabase_rest",
            ok=False,
            message=f"Missing env vars: {', '.join(missing)}",
        )

    base_url = os.environ["SUPABASE_URL"].rstrip("/")
    service_role = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    url = f"{base_url}/rest/v1/profiles"
    headers = {
        "apikey": service_role,
        "Authorization": f"Bearer {service_role}",
    }
    params = {"select": "id", "limit": "1"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers, params=params)
        if response.status_code == 200:
            return CheckResult("supabase_rest", True, "REST query succeeded")
        return CheckResult(
            "supabase_rest",
            False,
            f"REST query failed with status {response.status_code}",
        )
    except Exception as exc:  # pragma: no cover - runtime environment dependent
        return CheckResult("supabase_rest", False, f"REST request error: {exc}")


async def check_database_url_direct() -> CheckResult:
    missing = _missing(["DATABASE_URL"])
    if missing:
        return CheckResult(
            "database_url_direct",
            False,
            "Missing env var: DATABASE_URL",
        )

    database_url = os.environ["DATABASE_URL"]
    conn: asyncpg.Connection | None = None
    try:
        conn = await asyncpg.connect(database_url, timeout=10.0)
        await conn.fetchval("SELECT 1")
        return CheckResult("database_url_direct", True, "Direct Postgres connection succeeded")
    except Exception as exc:  # pragma: no cover - runtime environment dependent
        return CheckResult("database_url_direct", False, f"Direct connection error: {exc}")
    finally:
        if conn is not None:
            await conn.close()


async def check_openrouter_chat() -> CheckResult:
    required = ["OPENROUTER_API_KEY"]
    missing = _missing(required)
    if missing:
        return CheckResult(
            name="openrouter_chat",
            ok=False,
            message=f"Missing env vars: {', '.join(missing)}",
        )

    api_key = os.environ["OPENROUTER_API_KEY"]
    model = os.getenv("OPENROUTER_CHECK_MODEL", "openai/gpt-4o-mini")
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 1,
        "temperature": 0,
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(url, headers=headers, json=payload)
        if response.status_code == 200:
            return CheckResult("openrouter_chat", True, f"Chat completion succeeded ({model})")
        return CheckResult(
            "openrouter_chat",
            False,
            f"Chat completion failed with status {response.status_code}",
        )
    except Exception as exc:  # pragma: no cover - runtime environment dependent
        return CheckResult("openrouter_chat", False, f"OpenRouter request error: {exc}")


async def check_langfuse() -> CheckResult:
    required = ["LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"]
    missing = _missing(required)
    if missing:
        return CheckResult(
            name="langfuse",
            ok=False,
            message=f"Missing env vars: {', '.join(missing)}",
        )

    host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com").rstrip("/")
    url = f"{host}/api/public/health"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
        if response.status_code == 200:
            return CheckResult("langfuse", True, "Health endpoint reachable")
        return CheckResult("langfuse", False, f"Health endpoint status {response.status_code}")
    except Exception as exc:  # pragma: no cover - runtime environment dependent
        return CheckResult("langfuse", False, f"Health request error: {exc}")


async def main() -> int:
    checks: list[Callable[[], Awaitable[CheckResult]]] = [
        check_supabase_rest,
        check_database_url_direct,
        check_openrouter_chat,
        check_langfuse,
    ]
    results: list[CheckResult] = []
    for check in checks:
        results.append(await check())

    print("Connection checks:")
    for result in results:
        status = "OK" if result.ok else "FAIL"
        print(f"- {result.name}: {status} - {result.message}")

    failures = [r for r in results if not r.ok]
    if failures:
        print(f"\nSummary: {len(failures)} integration(s) FAIL.")
        return 1

    print("\nSummary: all integrations OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
