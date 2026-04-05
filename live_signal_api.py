"""
live_signal_api.py
==================
FastAPI SSE endpoint wrapping LiveSignalStream.

Run:
    uvicorn live_signal_api:app --reload

POST /score          — push alpha + external scores
GET  /stream         — SSE stream of SignalSnapshot events
GET  /snapshot       — latest snapshot (polling fallback)
GET  /health         — liveness check
"""

from __future__ import annotations

import json
import asyncio
import logging
from typing import AsyncIterator, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from drift_live_signal import LiveSignalStream, SignalSnapshot

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App + shared stream instance
# ---------------------------------------------------------------------------

app = FastAPI(title="drift_orchestrator live signal API", version="1.0.0")

# A single shared stream; replace with a session-keyed map for multi-session.
_stream = LiveSignalStream(session_id="default", queue_maxsize=128)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ScoreUpdate(BaseModel):
    alpha: float = Field(..., ge=0.0, le=1.0, description="Internal drift score 0-1")
    external: float = Field(..., ge=0.0, le=1.0, description="External evaluator score 0-1")
    session_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "subscribers": _stream.subscriber_count,
        "seq": _stream.seq,
    }


@app.get("/snapshot")
async def snapshot() -> JSONResponse:
    snap = _stream.last_snapshot
    if snap is None:
        return JSONResponse({"error": "no snapshot yet"}, status_code=204)
    return JSONResponse(snap.as_dict())


@app.post("/score")
async def push_score(update: ScoreUpdate) -> JSONResponse:
    snap = await _stream.update_scores(update.alpha, update.external)
    if snap is None:
        return JSONResponse({"status": "no_change"})
    return JSONResponse({"status": "emitted", "seq": snap.seq, "snapshot": snap.as_dict()})


@app.get("/stream")
async def sse_stream(request: Request) -> StreamingResponse:
    """
    SSE endpoint. Each event is framed as:
        data: <json>\n\n

    Sends an initial snapshot immediately if one exists, then streams
    subsequent deltas. Cleans up subscription on client disconnect.
    """
    return StreamingResponse(
        _sse_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


async def _sse_generator(request: Request) -> AsyncIterator[str]:
    """
    Async generator for SSE frames.
    Subscribes to the shared stream, yields JSON frames,
    and cleans up on client disconnect or generator exit.
    """
    q = await _stream.subscribe()
    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                snapshot: SignalSnapshot = await asyncio.wait_for(q.get(), timeout=15.0)
                payload = json.dumps(snapshot.as_dict())
                yield f"data: {payload}\n\n"
            except asyncio.TimeoutError:
                # keepalive comment
                yield ": keepalive\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        await _stream.unsubscribe(q)


# ---------------------------------------------------------------------------
# Dev entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("live_signal_api:app", host="0.0.0.0", port=8765, reload=True)
