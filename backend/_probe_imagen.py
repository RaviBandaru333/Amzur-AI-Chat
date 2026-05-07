"""Probe LiteLLM proxy for which Imagen alias works."""
from app.ai.llm import get_llm_client
from app.core.config import settings

client = get_llm_client()
candidates = [
    "gemini/imagen-4.0-fast-generate-001",
    "imagen-4.0-fast-generate-001",
    "vertex_ai/imagen-4.0-fast-generate-001",
    "imagen-4.0-generate-001",
    "imagen-3.0-fast-generate-001",
    "dall-e-3",
]
prompt = "A serene sunrise over a quiet village pond."
for cand in candidates:
    print(f"--- Trying model: {cand}")
    try:
        resp = client.images.generate(model=cand, prompt=prompt, user="probe@x")
        first = resp.data[0] if resp.data else None
        if first:
            url = getattr(first, "url", None)
            b64 = getattr(first, "b64_json", None)
            print(f"  OK: url={bool(url)} b64={bool(b64)}")
        else:
            print("  OK but empty data")
        break
    except Exception as exc:
        print(f"  FAIL: {type(exc).__name__}: {str(exc)[:200]}")
print("Done. Settings.IMAGE_GEN_MODEL =", settings.IMAGE_GEN_MODEL)
