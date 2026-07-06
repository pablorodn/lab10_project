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


def test_00006_is_additive_and_targets_profiles_default_model():
    migration = (_repo_root() / "migrations" / "00006_agent_total_scope.sql").read_text()
    executable_sql = _sql_without_comments(migration)

    assert "alter table public.profiles" in executable_sql
    assert "add column default_model text" in executable_sql

    # Structural safety for Phase 1: no destructive statements in executable SQL.
    assert "drop table" not in executable_sql
    assert "delete from" not in executable_sql
    assert "alter table public.profiles drop column" not in executable_sql


def test_00006_has_reasonable_forward_compatibility_and_rollback_note():
    initial_schema = (_repo_root() / "migrations" / "00001_initial_schema.sql").read_text().lower()
    migration = (_repo_root() / "migrations" / "00006_agent_total_scope.sql").read_text().lower()

    # Forward compatibility: base schema already has profiles, and not this column yet.
    assert "create table public.profiles" in initial_schema
    assert "default_model" not in initial_schema

    # Rollback note exists (documented, not executed in this local structural test).
    assert "rollback razonable" in migration
    assert "drop column if exists default_model" in migration
