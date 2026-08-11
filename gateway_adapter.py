#!/usr/bin/env python3
"""Public HTTP adapter for drift_orchestrator experiment reruns.

This implements the /route and /health contract used by the historical probe
scripts without requiring the private sibling localai_gateway repository.

The response contract is intentionally compatible with the historical gateway,
but fresh inference remains dependent on the local Ollama/model/runtime stack.
"""

from __future__ import annotations

import os
import time
import uuid

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
GATEWAY_HOST = os.getenv("GATEWAY_HOST", "127.0.0.1")
GATEWAY_PORT = int(os.getenv("GATEWAY_PORT", "8765"))
GATEWAY_MODEL = os.getenv("GATEWAY_MODEL", "qwen2.5:3b")


class RouteRequest(BaseModel):
    prompt: str
    drift_score: float = 0.0
    tier: str = "fast"


class RouteResponse(BaseModel):
    response: str
    model: str
    tier: str
    drift_score: float
    latency_ms: float
    request_id: str


def call_ollama(prompt: str, model: str) -> str:
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    with httpx.Client(timeout=180.0) as client:
        response = client.post(f"{OLLAMA_HOST}/api/chat", json=body)
        response.raise_for_status()
        payload = response.json()

    try:
        return payload["message"]["content"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError("unexpected Ollama /api/chat response shape") from exc


app = FastAPI(title="drift_orchestrator gateway adapter", version="1.0.0")


@app.post("/route", response_model=RouteResponse)
def route(req: RouteRequest) -> RouteResponse:
    request_id = str(uuid.uuid4())[:8]
    started = time.monotonic()
    try:
        text = call_ollama(req.prompt, GATEWAY_MODEL)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Ollama error: {exc}") from exc

    latency_ms = round((time.monotonic() - started) * 1000, 1)
    return RouteResponse(
        response=text,
        model=GATEWAY_MODEL,
        tier=req.tier or "fast",
        drift_score=req.drift_score,
        latency_ms=latency_ms,
        request_id=request_id,
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "ollama": OLLAMA_HOST,
        "model": GATEWAY_MODEL,
    }


if __name__ == "__main__":
    uvicorn.run(app, host=GATEWAY_HOST, port=GATEWAY_PORT)
