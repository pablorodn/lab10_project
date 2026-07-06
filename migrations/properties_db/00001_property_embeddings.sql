-- ============================================================
-- 00001_property_embeddings
-- Búsqueda semántica sobre public.properties (proyecto Supabase separado,
-- solo propiedades — NO es el proyecto Supabase de esta app).
--
-- Tabla separada en vez de una columna `embedding` en `properties`: el
-- scraper hace upsert directo sobre `properties` en cada corrida, y no debe
-- pisar ni depender de una columna de embedding que vive en esa misma fila.
-- Desacoplar el embedding en su propia tabla (FK 1:1 por property_id) permite
-- que el ciclo de vida de escritura del scraper y el de un backfill de
-- embeddings (futuro, no incluido en esta migración) evolucionen
-- independientemente sin pisarse.
--
-- `content_hash` guarda el hash del documento compuesto que se embebió
-- (ej. título + descripción + barrio + etc.), para que un script de backfill
-- futuro pueda comparar contra el estado actual de la fila y saltarse las
-- que no cambiaron, sin necesidad de re-embeber todo el dataset en cada
-- corrida.
-- ============================================================

-- Puede ya estar habilitada en el proyecto; idempotente.
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE public.property_embeddings (
  property_id uuid        PRIMARY KEY REFERENCES public.properties(id) ON DELETE CASCADE,
  embedding   vector(1536),
  content_hash text        NOT NULL,
  embedded_at timestamptz NOT NULL DEFAULT now()
);

-- HNSW en vez de IVFFlat: esta tabla crece con cada scrapeo, y un índice
-- IVFFlat necesita elegir `lists` en función del tamaño de la tabla y
-- re-entrenarse (reindexar) a medida que esta crece para no degradar el
-- recall. HNSW no tiene ese parámetro de "tamaño esperado" ni requiere
-- reindexación periódica. Se dejan los defaults de pgvector para
-- m/ef_construction — no hace falta tunear todavía con el volumen actual.
CREATE INDEX property_embeddings_embedding_idx
  ON public.property_embeddings USING hnsw (embedding vector_cosine_ops);

-- ============================================================
-- Rollback razonable:
--   DROP INDEX IF EXISTS public.property_embeddings_embedding_idx;
--   DROP TABLE IF EXISTS public.property_embeddings;
--   -- (no se incluye DROP EXTENSION vector: puede estar en uso por otra
--   -- tabla del mismo proyecto)
-- ============================================================
