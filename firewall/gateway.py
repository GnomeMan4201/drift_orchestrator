from fastapi import FastAPI
import httpx

app = FastAPI()

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
MODEL = "qwen2.5:3b"

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/route")
async def route(req: dict):
    try:
        prompt = req.get("prompt", "")
        options = req.get("options", {})
        async with httpx.AsyncClient(timeout=180) as client:
            r = await client.post(
                OLLAMA_URL,
                json={"model": MODEL, "prompt": prompt, "stream": False, "options": options},
            )
            r.raise_for_status()
        data = r.json()
        return {"response": data.get("response", "")}
    except Exception as e:
        print("GATEWAY FAILURE:", repr(e))
        return {"response": "[MODEL ERROR]"}

OLLAMA_EMBED_URL = "http://127.0.0.1:11434/api/embeddings"
EMBED_MODEL = "nomic-embed-text"

@app.post("/embed")
async def embed(req: dict):
    try:
        text = req.get("text", "")
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                OLLAMA_EMBED_URL,
                json={"model": EMBED_MODEL, "prompt": text},
            )
            r.raise_for_status()
        return {"embedding": r.json()["embedding"]}
    except Exception as e:
        print("EMBED FAILURE:", repr(e))
        return {"embedding": []}
