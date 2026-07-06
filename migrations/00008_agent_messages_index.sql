-- ============================================================
-- 00008_agent_messages_index
-- agent_messages no tenía ningún índice sobre session_id (Postgres no crea
-- uno automático sobre columnas de FK). Es la tabla de mayor crecimiento del
-- esquema y se consulta en cada render de chat y en cada turno del agente
-- (flush de memoria, título de sesión), siempre filtrando por session_id y
-- ordenando por created_at.
-- ============================================================
CREATE INDEX idx_agent_messages_session_created
  ON public.agent_messages (session_id, created_at);

-- ============================================================
-- Rollback razonable:
--   DROP INDEX IF EXISTS public.idx_agent_messages_session_created;
-- ============================================================
