---
name: run-server
description: Launch and verify the FastAPI dev server for lab10_project (uvicorn), poll for readiness, and know how to stop it. Use whenever asked to run, start, restart, or smoke-test this app locally.
---

# Run the lab10_project server

FastAPI + uvicorn app, no `if __name__` entrypoint — always launched via `uvicorn app.main:app`. No Makefile/script wraps this; use the commands below directly.

## Prerequisites

- Deps already installed via `uv` (`uv sync --extra dev --extra scripts` if a fresh checkout).
- `.env` must exist at repo root with `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `OPENROUTER_API_KEY`, `SECRET_KEY`.

**Important**: as of this writing, `.env` in this repo points at a **hosted/production** Supabase project (not local Postgres) — `DATABASE_URL`/`SUPABASE_URL` resolve to a real `*.supabase.co` host. Before running interactively (logging in, sending chat messages), confirm with the user whether that's still the case and whether it's OK to write real data (sessions/messages/memories) against it. Don't assume a fresh `.env` is safe just because the command runs locally.

## Run (background-launch pattern)

```bash
pkill -f "uvicorn app.main:app" 2>/dev/null; sleep 1  # kill any stale instance first

SCRATCH="<use the session's scratchpad dir, or /tmp if none>"
uv run uvicorn app.main:app --port 8000 --host 127.0.0.1 &> "$SCRATCH/server.log" &
disown
```

Then wait for readiness (there is no `/health` endpoint — use `/login`, which is public and always returns 200 once the app has started):

```bash
for i in $(seq 1 30); do
  curl -sf -o /dev/null http://127.0.0.1:8000/login && echo "UP after ${i}s" && break
  sleep 1
done
```

What "ready" looks like in the log (`tail -n 20 "$SCRATCH/server.log"`):

```
{"...", "message": "Agent runtime warmed up.", "event": "runtime_warmup"}
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

If `runtime_warmup_failed` appears instead of `runtime_warmup`, the checkpointer pool couldn't reach Postgres — check `DATABASE_URL` before going further.

## Verify

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/login   # expect 200
curl -s -o /dev/null -w "%{http_code} -> %{redirect_url}\n" http://127.0.0.1:8000/  # expect 307 -> /login when logged out
```

`/` redirecting to `/login` with 307 confirms `AuthMiddleware` is wired correctly (this is expected, not a bug — every route except `/login`/`/signup`/static requires auth).

## Stop

```bash
pkill -f "uvicorn app.main:app"
```

## Logs

Everything the app logs is structured JSON on stdout/stderr — `grep`/`tail` the file from `&>` above. Per-request lines carry `route`, `status`, `latency_ms`. Chat turns additionally log `db_ms`/`agent_ms`/`total_ms` under `event: chat_processed` / `chat_stream_processed` — check these first for any "slow response" complaint before suspecting infra.

## Known noise (not bugs)

- `LANGFUSE_HOST` in `.env` may point to `http://localhost:3000` — if nothing is listening there, every chat turn will log repeated `opentelemetry.exporter.otlp...Connection refused` warnings and add real latency (each retry round costs several seconds, blocking). Not a code regression; either start the local Langfuse instance or unset `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` to disable tracing locally (`create_langfuse_callback()` in `app/agent/langfuse.py` returns `None` when either key is empty).
- A first chat turn on a long-lived session may trigger `LLM compaction failed; falling back to microcompact` — this is `app/agent/compaction.py` handling an oversized message (e.g. a large multimodal attachment block) it can't summarize; it self-heals via the `microcompact` fallback once the session crosses `COMPACTION_TAIL_SIZE` (10) messages, at real cost of one slow failed LLM call. Not related to server startup.
