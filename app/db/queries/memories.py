from supabase import AsyncClient


async def save_memory(
    db: AsyncClient,
    user_id: str,
    memory_type: str,
    content: str,
    embedding: list[float],
) -> None:
    await db.table("memories").insert(
        {
            "user_id": user_id,
            "type": memory_type,
            "content": content,
            "embedding": embedding,
        }
    ).execute()


async def match_memories(db: AsyncClient, user_id: str, query_embedding: list[float], limit: int = 8) -> list[dict]:
    result = await db.rpc(
        "match_memories",
        {"query_embedding": query_embedding, "match_user_id": user_id, "match_count": limit},
    ).execute()
    return result.data or []


async def increment_memory_retrieval_count(db: AsyncClient, memory_ids: list[str]) -> None:
    if not memory_ids:
        return
    await db.rpc("increment_memory_retrieval_count", {"memory_ids": memory_ids}).execute()
