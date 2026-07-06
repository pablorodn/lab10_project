-- ============================================================
-- 00002_match_properties_rpc
-- RPC de búsqueda combinada (semántica + filtros estructurados) sobre
-- public.properties, para ser llamada desde la app vía cliente Supabase con
-- anon key (ver 00003_rls_readonly_anon.sql).
--
-- SECURITY INVOKER (no DEFINER): la función corre con los privilegios de
-- quien la invoca (el rol anon, una vez otorgado EXECUTE), respetando RLS
-- de `properties` en vez de saltársela con privilegios de owner.
--
-- LEFT JOIN contra property_embeddings (en vez de INNER JOIN): una
-- propiedad puede no tener embedding todavía si el backfill (script futuro,
-- no incluido en esta migración) no corrió sobre ella aún. El filtrado
-- estructurado (operation_type, precio, barrio, etc.) debe poder devolver
-- esa propiedad igual, simplemente sin ranking semántico ni `similarity`
-- (quedan NULL en el resultado).
-- ============================================================

CREATE OR REPLACE FUNCTION public.match_properties(
  query_embedding     vector(1536) default null,
  p_operation_type    text         default null,
  p_property_type     text         default null,
  p_neighborhood      text         default null,
  p_comuna            text         default null,
  p_min_bedrooms      int          default null,
  p_min_bathrooms     int          default null,
  p_min_parking       int          default null,
  p_min_price_cop     bigint       default null,
  p_max_price_cop     bigint       default null,
  p_min_area_m2       numeric      default null,
  p_stratum           int          default null,
  match_count         int          default 8
)
RETURNS TABLE (
  id             uuid,
  title          text,
  operation_type text,
  property_type  text,
  price_cop      bigint,
  area_m2        numeric,
  bedrooms       integer,
  bathrooms      integer,
  parking_spots  integer,
  neighborhood   text,
  comuna         text,
  stratum        integer,
  listing_url    text,
  similarity     float
)
LANGUAGE SQL STABLE
SECURITY INVOKER
AS $$
  SELECT
    p.id,
    p.title,
    p.operation_type,
    p.property_type,
    p.price_cop,
    p.area_m2,
    p.bedrooms,
    p.bathrooms,
    p.parking_spots,
    p.neighborhood,
    p.comuna,
    p.stratum,
    p.listing_url,
    CASE
      WHEN query_embedding IS NULL OR pe.embedding IS NULL THEN NULL
      ELSE 1 - (pe.embedding <=> query_embedding)
    END AS similarity
  FROM public.properties p
  LEFT JOIN public.property_embeddings pe ON pe.property_id = p.id
  WHERE p.is_active = true
    AND (p_operation_type IS NULL OR p.operation_type = p_operation_type)
    AND (p_property_type  IS NULL OR p.property_type  = p_property_type)
    AND (p_neighborhood   IS NULL OR p.neighborhood ILIKE '%' || p_neighborhood || '%')
    AND (p_comuna         IS NULL OR p.comuna = p_comuna)
    AND (p_min_bedrooms   IS NULL OR p.bedrooms      >= p_min_bedrooms)
    AND (p_min_bathrooms  IS NULL OR p.bathrooms     >= p_min_bathrooms)
    AND (p_min_parking    IS NULL OR p.parking_spots >= p_min_parking)
    AND (p_min_price_cop  IS NULL OR p.price_cop     >= p_min_price_cop)
    AND (p_max_price_cop  IS NULL OR p.price_cop     <= p_max_price_cop)
    AND (p_min_area_m2    IS NULL OR p.area_m2       >= p_min_area_m2)
    AND (p_stratum        IS NULL OR p.stratum       = p_stratum)
  ORDER BY
    pe.embedding <=> query_embedding ASC NULLS LAST,
    p.price_cop ASC
  LIMIT LEAST(match_count, 15);
$$;

-- ============================================================
-- Rollback razonable:
--   DROP FUNCTION IF EXISTS public.match_properties(
--     vector, text, text, text, text, int, int, int, bigint, bigint,
--     numeric, int, int
--   );
-- ============================================================
