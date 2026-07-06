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


def test_00009_is_additive_replace_of_existing_match_memories_function():
    migration = (_repo_root() / "migrations" / "00009_tune_match_memories_probes.sql").read_text()
    executable_sql = _sql_without_comments(migration)

    assert "create or replace function match_memories(" in executable_sql
    assert "set ivfflat.probes = 10" in executable_sql

    # Structural safety: CREATE OR REPLACE FUNCTION, nada destructivo.
    assert "drop table" not in executable_sql
    assert "delete from" not in executable_sql
    assert "drop function" not in executable_sql


def test_00009_has_reasonable_forward_compatibility_and_rollback_note():
    original_definition = (_repo_root() / "migrations" / "00004_long_term_memory.sql").read_text().lower()
    migration = (_repo_root() / "migrations" / "00009_tune_match_memories_probes.sql").read_text().lower()

    # Forward compatibility: match_memories ya existe desde 00004, sin la
    # clausula SET ivfflat.probes que agrega esta migracion.
    assert "create or replace function match_memories(" in original_definition
    assert "ivfflat.probes" not in original_definition

    # Rollback note existe (documentado, no ejecutado en este test estructural):
    # volver al mismo cuerpo de 00004 sin la clausula SET.
    assert "rollback razonable" in migration
    assert "sin la cláusula set" in migration
