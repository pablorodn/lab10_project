from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _sql_without_comments(sql: str) -> str:
    lines = []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--"):
            continue
        lines.append(line)
    return "\n".join(lines).lower()


def test_00008_is_additive_and_targets_existing_agent_messages_table():
    migration = (_repo_root() / "migrations" / "00008_agent_messages_index.sql").read_text()
    executable_sql = _sql_without_comments(migration)

    assert "create index idx_agent_messages_session_created" in executable_sql
    assert "on public.agent_messages (session_id, created_at)" in executable_sql

    # Structural safety: es un CREATE INDEX puro, nada destructivo.
    assert "drop table" not in executable_sql
    assert "delete from" not in executable_sql
    assert "drop column" not in executable_sql
    assert "drop index" not in executable_sql


def test_00008_has_reasonable_forward_compatibility_and_rollback_note():
    initial_schema = (_repo_root() / "migrations" / "00001_initial_schema.sql").read_text().lower()
    migration = (_repo_root() / "migrations" / "00008_agent_messages_index.sql").read_text().lower()

    # Forward compatibility: agent_messages ya existe desde 00001, sin este indice.
    assert "create table public.agent_messages" in initial_schema
    assert "idx_agent_messages_session_created" not in initial_schema

    # Rollback note existe (documentado, no ejecutado en este test estructural).
    assert "rollback razonable" in migration
    assert "drop index if exists public.idx_agent_messages_session_created" in migration
