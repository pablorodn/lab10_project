-- Add last_used_at to agent_sessions for tracking current session per channel
ALTER TABLE public.agent_sessions
  ADD COLUMN last_used_at timestamptz NOT NULL DEFAULT now();

-- Backfill existing rows
UPDATE public.agent_sessions SET last_used_at = COALESCE(updated_at, created_at);

-- Index for fast "current session" lookup per user+channel
CREATE INDEX idx_sessions_current
  ON public.agent_sessions (user_id, channel, status, last_used_at DESC);
