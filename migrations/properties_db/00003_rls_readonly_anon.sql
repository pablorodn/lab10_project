-- ============================================================
-- 00003_rls_readonly_anon
-- La app consume esta tabla desde un segundo proyecto Supabase, dedicado
-- solo a propiedades, usando un cliente Supabase separado del de la app
-- (variables `PROPERTIES_SUPABASE_URL` / `PROPERTIES_SUPABASE_ANON_KEY`,
-- distintas de las `SUPABASE_*` que usa el resto del repo). Ese cliente se
-- autentica con la anon key, nunca con service role: este proyecto Supabase
-- se usa exclusivamente de lectura para búsqueda de propiedades, no maneja
-- usuarios ni escritura desde la app. RLS + policy de solo-lectura sobre
-- filas activas es lo que hace seguro exponer la anon key para este uso.
-- ============================================================

ALTER TABLE public.properties ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anon can read active properties"
  ON public.properties FOR SELECT
  TO anon
  USING (is_active = true);

-- Necesario para que la policy de RLS aplique: sin GRANT SELECT, el rol
-- anon no puede ni empezar a leer la tabla, sin importar la policy.
GRANT SELECT ON public.properties TO anon;

-- Necesario para invocar match_properties() (00002_match_properties_rpc.sql)
-- desde el cliente anon.
GRANT EXECUTE ON FUNCTION public.match_properties(
  vector, text, text, text, text, int, int, int, bigint, bigint,
  numeric, int, int
) TO anon;

-- ============================================================
-- Rollback razonable:
--   REVOKE EXECUTE ON FUNCTION public.match_properties(
--     vector, text, text, text, text, int, int, int, bigint, bigint,
--     numeric, int, int
--   ) FROM anon;
--   REVOKE SELECT ON public.properties FROM anon;
--   DROP POLICY IF EXISTS "Anon can read active properties" ON public.properties;
--   ALTER TABLE public.properties DISABLE ROW LEVEL SECURITY;
-- ============================================================
