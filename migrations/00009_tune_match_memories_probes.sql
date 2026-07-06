-- ============================================================
-- 00009_tune_match_memories_probes
-- match_memories() (definida en 00004_long_term_memory.sql) no fijaba
-- ivfflat.probes, así que corría con el default de la sesión (probes=1).
-- Con lists=100 en memories_embedding_idx, probes=1 solo escanea ~1% de los
-- clusters del índice: el recall de la búsqueda semántica se degrada
-- silenciosamente (sin error, solo memorias relevantes no devueltas) a
-- medida que crece la tabla. Se sube a 10 probes como default razonable,
-- sacrificando algo de velocidad por recall. CREATE OR REPLACE mantiene el
-- cuerpo idéntico, solo agrega la cláusula SET a nivel de función.
-- ============================================================
CREATE OR REPLACE FUNCTION match_memories(
  query_embedding   vector(1536),
  match_user_id     UUID,
  match_count       INT DEFAULT 8
)
RETURNS TABLE (
  id                UUID,
  type              TEXT,
  content           TEXT,
  retrieval_count   INT,
  similarity        FLOAT
)
LANGUAGE SQL STABLE
SET ivfflat.probes = 10
AS $$
  SELECT
    id,
    type,
    content,
    retrieval_count,
    1 - (embedding <=> query_embedding) AS similarity
  FROM memories
  WHERE user_id = match_user_id
    AND embedding IS NOT NULL
  ORDER BY embedding <=> query_embedding
  LIMIT match_count;
$$;

-- ============================================================
-- Rollback razonable:
--   CREATE OR REPLACE FUNCTION match_memories(...) LANGUAGE SQL STABLE AS $$ ... $$;
--   (mismo cuerpo que en 00004_long_term_memory.sql, sin la cláusula SET)
-- ============================================================
