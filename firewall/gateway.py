from fastapi import FastAPI
import httpx

app = FastAPI()

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
MODEL = "mistral:latest"

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/route")
async def route(req: dict):
    prompt = req.get("prompt", "")

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "prompt": prompt,
                "stream": False,
            },
        )
        r.raise_for_status()

    data = r.json()
    return {"response": data.get("response", "")}
