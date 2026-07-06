import httpx

from app.config import get_settings

EMBEDDING_MODEL = "openai/text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


async def generate_embedding(text: str) -> list[float]:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://openrouter.ai/api/v1/embeddings",
            headers={
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "HTTP-Referer": "https://agents.local",
            },
            json={"model": EMBEDDING_MODEL, "input": text, "dimensions": EMBEDDING_DIMENSIONS},
        )
        response.raise_for_status()
        data = response.json()
        return data["data"][0]["embedding"]
