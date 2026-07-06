-- ============================================================
-- 00005_tool_call_model_id
-- Distingue el UUID de auditoría (tool_calls.id) del id del tool call
-- emitido por el modelo (tc["id"] de LangChain). Este último es necesario
-- para reconstruir el ToolMessage(tool_call_id=...) correcto al reanudar
-- un flujo HITL tras un refresh de página.
-- Forward-compatible: columna nullable; filas existentes quedan en NULL.
-- ============================================================
ALTER TABLE public.tool_calls
  ADD COLUMN model_tool_call_id text;

-- Búsqueda del registro pendiente por (sesión, id del modelo) al reanudar.
CREATE INDEX idx_tool_calls_model_id
  ON public.tool_calls (session_id, model_tool_call_id);

-- ============================================================
-- Rollback razonable:
--   DROP INDEX IF EXISTS public.idx_tool_calls_model_id;
--   ALTER TABLE public.tool_calls DROP COLUMN IF EXISTS model_tool_call_id;
-- ============================================================
