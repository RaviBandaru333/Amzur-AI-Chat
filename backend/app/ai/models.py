"""Fetch and manage available models from LiteLLM proxy."""
import httpx
from app.core.config import settings


async def get_available_models() -> list[dict]:
    """Fetch all available models from LiteLLM proxy."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{settings.LITELLM_PROXY_URL}/v1/models",
                headers={"Authorization": f"Bearer {settings.LITELLM_API_KEY}"},
            )
            resp.raise_for_status()
            data = resp.json()

            # Include ALL models from LiteLLM
            models = data.get("data", [])
            available_models = []

            for model in models:
                model_id = model.get("id", "")
                
                # Create friendly name
                if "gemini" in model_id.lower():
                    provider = "Google"
                    name = model_id.replace("gemini/", "").replace("-", " ").title()
                elif "gpt" in model_id.lower():
                    provider = "OpenAI"
                    name = model_id.upper()
                elif "embedding" in model_id.lower():
                    provider = "OpenAI"
                    name = model_id.replace("-", " ").title()
                elif "imagen" in model_id.lower():
                    provider = "Google"
                    name = model_id.replace("gemini/", "").replace("-", " ").title()
                else:
                    provider = "Other"
                    name = model_id.replace("-", " ").title()

                available_models.append(
                    {
                        "id": model_id,
                        "name": name,
                        "provider": provider,
                    }
                )

            return available_models
    except Exception as e:
        print(f"Error fetching models from LiteLLM: {e}")
        # Fallback to default models
        return [
            {"id": "gpt-4o", "name": "GPT-4o", "provider": "OpenAI"},
            {
                "id": "gemini/gemini-2.5-flash",
                "name": "Gemini 2.5 Flash",
                "provider": "Google",
            },
            {
                "id": "text-embedding-3-large",
                "name": "Text Embedding 3 Large",
                "provider": "OpenAI",
            },
            {
                "id": "gemini/imagen-4.0-fast-generate-001",
                "name": "Imagen 4.0 Fast Generate",
                "provider": "Google",
            },
        ]

