-- ============================================================
-- 00007_sessions_title_and_archive
-- Fase 13 de agent_total: título automático de sesión y archivado/eliminación.
-- Cambios aditivos y compatibles hacia atrás:
--   - agent_sessions.title: nullable, sin default explícito (NULL por defecto).
--   - agent_sessions.status: se amplía el CHECK existente para admitir 'archived'
--     además de los valores ya soportados ('active', 'closed').
-- ============================================================
ALTER TABLE public.agent_sessions
  ADD COLUMN title text;

ALTER TABLE public.agent_sessions
  DROP CONSTRAINT IF EXISTS agent_sessions_status_check;

ALTER TABLE public.agent_sessions
  ADD CONSTRAINT agent_sessions_status_check
  CHECK (status IN ('active', 'archived', 'closed'));

-- ============================================================
-- Rollback razonable:
--   ALTER TABLE public.agent_sessions DROP COLUMN IF EXISTS title;
--   ALTER TABLE public.agent_sessions DROP CONSTRAINT IF EXISTS agent_sessions_status_check;
--   ALTER TABLE public.agent_sessions ADD CONSTRAINT agent_sessions_status_check
--     CHECK (status IN ('active', 'closed'));
-- Nota: el rollback del CHECK solo es seguro si no quedan filas con
-- status = 'archived' al momento de revertir.
-- Nota de control de cambios: cualquier DROP futuro de este cambio es
-- opcional y requiere autorización explícita separada del usuario.
-- ============================================================
