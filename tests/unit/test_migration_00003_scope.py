"""Bloque C5 (Fase 5): a diferencia de test_migration_00006/00008/00009_scope.py,
este archivo NO incluye un test de "rollback razonable". migrations/00003_scheduled_tasks.sql
es anterior a esa convencion (empezo recien en 00005_tool_call_model_id.sql;
confirmado con `grep -l -i "rollback" migrations/*.sql`, que no matchea 00001-00004)
y, por guardrails.mdc, una migracion ya mergeada no se modifica retroactivamente
-- ni siquiera para agregarle un comentario. Este test se limita a lo que
realmente se puede verificar sobre el archivo tal cual existe hoy: que es
aditivo y compatible hacia adelante."""

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


def test_00003_creates_new_scheduled_tasks_tables_not_present_before():
    initial_schema = (_repo_root() / "migrations" / "00001_initial_schema.sql").read_text().lower()
    session_management = (
        _repo_root() / "migrations" / "00002_session_management.sql"
    ).read_text().lower()
    migration = (_repo_root() / "migrations" / "00003_scheduled_tasks.sql").read_text()
    executable_sql = _sql_without_comments(migration)

    # Forward compatibility: scheduled_tasks/scheduled_task_runs son tablas
    # nuevas -- no existian en el esquema inicial ni en la migracion previa.
    assert "scheduled_tasks" not in initial_schema
    assert "scheduled_tasks" not in session_management

    assert "create table public.scheduled_tasks" in executable_sql
    assert "create table public.scheduled_task_runs" in executable_sql


def test_00003_is_additive_with_no_destructive_statements():
    migration = (_repo_root() / "migrations" / "00003_scheduled_tasks.sql").read_text()
    executable_sql = _sql_without_comments(migration)

    # El unico cambio sobre una tabla preexistente (agent_sessions) es aditivo:
    # reemplaza un CHECK constraint para permitir un valor nuevo de channel,
    # no toca columnas ni filas existentes.
    assert "alter table public.agent_sessions" in executable_sql
    assert "add constraint agent_sessions_channel_check" in executable_sql
    assert "check (channel in ('web', 'cron'))" in executable_sql

    # El resto son objetos nuevos (tablas, indices, policies de RLS).
    assert "create index idx_scheduled_tasks_due" in executable_sql
    assert "create index idx_task_runs_task_id" in executable_sql
    assert "create policy" in executable_sql

    # Structural safety: nada destructivo sobre datos/estructura existentes.
    assert "drop table" not in executable_sql
    assert "delete from" not in executable_sql
    assert "drop column" not in executable_sql
    assert "alter table public.agent_sessions drop" not in executable_sql
