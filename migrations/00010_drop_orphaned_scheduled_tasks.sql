-- ============================================================
-- 00010_drop_orphaned_scheduled_tasks
-- scheduled_tasks y scheduled_task_runs (creadas en 00003_scheduled_tasks.sql)
-- soportaban una feature de tareas programadas/cron que ya fue eliminada del
-- repo (app/routers/cron.py, app/services/scheduler.py y
-- app/services/cron_claim.py fueron borrados; confirmado via `git log
-- --diff-filter=D`, commit c5041ec). Hoy no existe ningun modulo Python que
-- consulte estas tablas (confirmado con `grep -rln "scheduled_task" app/` sin
-- resultados). Verificado antes de esta migracion: ambas tablas estan vacias
-- en produccion (SELECT count(*) = 0 en scheduled_tasks y en
-- scheduled_task_runs).
--
-- 00003 tambien agrego 'cron' como valor valido del CHECK de
-- agent_sessions.channel (unica forma en que esta feature tocaba una tabla
-- que si sigue en uso). Se verifico `SELECT count(*) FROM agent_sessions
-- WHERE channel = 'cron'` = 0 filas antes de decidir revertir ese constraint
-- tambien -- si hubiera habido alguna fila con ese valor, este bloque se
-- hubiera omitido y solo se habrian dropeado las dos tablas.
-- ============================================================

-- FK de scheduled_task_runs -> scheduled_tasks: dropear primero la tabla hija.
DROP TABLE IF EXISTS public.scheduled_task_runs;
DROP TABLE IF EXISTS public.scheduled_tasks;

-- Revertir agent_sessions.channel a su dominio original (sin 'cron'), ya que
-- ningun row de produccion usa ese valor hoy.
ALTER TABLE public.agent_sessions
  DROP CONSTRAINT IF EXISTS agent_sessions_channel_check;

ALTER TABLE public.agent_sessions
  ADD CONSTRAINT agent_sessions_channel_check
  CHECK (channel IN ('web'));

-- ============================================================
-- Rollback razonable:
--   ALTER TABLE public.agent_sessions
--     DROP CONSTRAINT IF EXISTS agent_sessions_channel_check;
--   ALTER TABLE public.agent_sessions
--     ADD CONSTRAINT agent_sessions_channel_check
--     CHECK (channel IN ('web', 'cron'));
--
--   CREATE TABLE public.scheduled_tasks (
--     id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
--     user_id       uuid        NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
--     prompt        text        NOT NULL,
--     schedule_type text        NOT NULL CHECK (schedule_type IN ('one_time', 'recurring')),
--     run_at        timestamptz,
--     cron_expr     text,
--     timezone      text        NOT NULL DEFAULT 'UTC',
--     status        text        NOT NULL DEFAULT 'active'
--                   CHECK (status IN ('active', 'paused', 'completed', 'failed')),
--     last_run_at   timestamptz,
--     next_run_at   timestamptz,
--     created_at    timestamptz NOT NULL DEFAULT now(),
--     updated_at    timestamptz NOT NULL DEFAULT now()
--   );
--
--   ALTER TABLE public.scheduled_tasks ENABLE ROW LEVEL SECURITY;
--
--   CREATE POLICY "Users can manage own scheduled tasks"
--     ON public.scheduled_tasks FOR ALL
--     USING (auth.uid() = user_id);
--
--   CREATE INDEX idx_scheduled_tasks_due
--     ON public.scheduled_tasks (status, next_run_at)
--     WHERE status = 'active';
--
--   CREATE TABLE public.scheduled_task_runs (
--     id                 uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
--     task_id            uuid        NOT NULL REFERENCES public.scheduled_tasks(id) ON DELETE CASCADE,
--     status             text        NOT NULL DEFAULT 'running'
--                        CHECK (status IN ('running', 'completed', 'failed')),
--     started_at         timestamptz NOT NULL DEFAULT now(),
--     finished_at        timestamptz,
--     error              text,
--     agent_session_id   uuid        REFERENCES public.agent_sessions(id) ON DELETE SET NULL,
--     notified           boolean     NOT NULL DEFAULT false,
--     notification_error text
--   );
--
--   ALTER TABLE public.scheduled_task_runs ENABLE ROW LEVEL SECURITY;
--
--   CREATE POLICY "Users can view own task runs"
--     ON public.scheduled_task_runs FOR SELECT
--     USING (
--       EXISTS (
--         SELECT 1 FROM public.scheduled_tasks t
--         WHERE t.id = scheduled_task_runs.task_id
--           AND t.user_id = auth.uid()
--       )
--     );
--
--   CREATE INDEX idx_task_runs_task_id
--     ON public.scheduled_task_runs (task_id, started_at DESC);
--   (misma definicion que en 00003_scheduled_tasks.sql)
-- ============================================================
