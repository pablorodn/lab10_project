-- ============================================================
-- Extend agent_sessions channel to support cron-triggered runs
-- ============================================================
ALTER TABLE public.agent_sessions
  DROP CONSTRAINT IF EXISTS agent_sessions_channel_check;

ALTER TABLE public.agent_sessions
  ADD CONSTRAINT agent_sessions_channel_check
  CHECK (channel IN ('web', 'cron'));

-- ============================================================
-- scheduled_tasks
-- ============================================================
CREATE TABLE public.scheduled_tasks (
  id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid        NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  prompt        text        NOT NULL,
  schedule_type text        NOT NULL CHECK (schedule_type IN ('one_time', 'recurring')),
  run_at        timestamptz,          -- for one_time: the target execution time
  cron_expr     text,                 -- for recurring: standard 5-field cron expression
  timezone      text        NOT NULL DEFAULT 'UTC',
  status        text        NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'paused', 'completed', 'failed')),
  last_run_at   timestamptz,
  next_run_at   timestamptz,          -- computed; used by the cron runner to find due tasks
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.scheduled_tasks ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own scheduled tasks"
  ON public.scheduled_tasks FOR ALL
  USING (auth.uid() = user_id);

-- Fast lookup for the cron runner (service-role bypasses RLS)
CREATE INDEX idx_scheduled_tasks_due
  ON public.scheduled_tasks (status, next_run_at)
  WHERE status = 'active';

-- ============================================================
-- scheduled_task_runs (audit log per execution)
-- ============================================================
CREATE TABLE public.scheduled_task_runs (
  id                 uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id            uuid        NOT NULL REFERENCES public.scheduled_tasks(id) ON DELETE CASCADE,
  status             text        NOT NULL DEFAULT 'running'
                     CHECK (status IN ('running', 'completed', 'failed')),
  started_at         timestamptz NOT NULL DEFAULT now(),
  finished_at        timestamptz,
  error              text,
  agent_session_id   uuid        REFERENCES public.agent_sessions(id) ON DELETE SET NULL,
  notified           boolean     NOT NULL DEFAULT false,
  notification_error text
);

ALTER TABLE public.scheduled_task_runs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own task runs"
  ON public.scheduled_task_runs FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM public.scheduled_tasks t
      WHERE t.id = scheduled_task_runs.task_id
        AND t.user_id = auth.uid()
    )
  );

CREATE INDEX idx_task_runs_task_id
  ON public.scheduled_task_runs (task_id, started_at DESC);
