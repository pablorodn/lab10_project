-- Enable pgvector extension (may already be enabled in Supabase)
CREATE EXTENSION IF NOT EXISTS vector;

-- Long-term memory store for the agent
CREATE TABLE memories (
  id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  type              TEXT        NOT NULL CHECK (type IN ('episodic', 'semantic', 'procedural')),
  content           TEXT        NOT NULL,
  embedding         vector(1536),
  retrieval_count   INT         NOT NULL DEFAULT 0,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_retrieved_at TIMESTAMPTZ
);

-- IVFFlat index for approximate nearest-neighbor cosine similarity search
-- lists=100 is a reasonable default for up to ~1M rows; tune upward as data grows
CREATE INDEX memories_embedding_idx
  ON memories USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

-- Index for efficient per-user filtering
CREATE INDEX memories_user_id_idx ON memories (user_id);

-- RPC function used by incrementRetrievalCount() in the agent
CREATE OR REPLACE FUNCTION increment_memory_retrieval_count(memory_ids UUID[])
RETURNS VOID
LANGUAGE SQL
AS $$
  UPDATE memories
  SET retrieval_count   = retrieval_count + 1,
      last_retrieved_at = NOW()
  WHERE id = ANY(memory_ids);
$$;

-- RPC function used by searchMemories() in the agent
-- Returns rows ordered by cosine similarity (highest first)
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
