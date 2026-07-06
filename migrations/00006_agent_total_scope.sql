-- ============================================================
-- 00006_agent_total_scope
-- Fase 1 de agent_total: agrega preferencia de modelo por usuario.
-- Cambio aditivo, nullable y compatible hacia atrás.
-- ============================================================
ALTER TABLE public.profiles
  ADD COLUMN default_model text;

-- ============================================================
-- Rollback razonable:
--   ALTER TABLE public.profiles DROP COLUMN IF EXISTS default_model;
-- Nota de control de cambios: cualquier DROP futuro de este cambio es
-- opcional y requiere autorización explícita separada del usuario.
-- ============================================================
