"""
live_signal_api.py
==================
FastAPI SSE endpoint wrapping LiveSignalStream.

Supports a session registry so AgentRuntime can register its own stream
and the dashboard subscribes to a real session's live telemetry.

Endpoints
---------
GET  /health                  — liveness, registry stats
GET  /sessions                — list active session IDs
GET  /stream                  — SSE from default session
GET  /stream/{session_id}     — SSE from a specific session
GET  /snapshot                — latest snapshot, default session
GET  /snapshot/{session_id}   — latest snapshot, specific session
POST /score                   — push scores to a session (or default)
POST /register/{session_id}   — create/touch a session stream entry

Run:
    uvicorn live_signal_api:app --port 8765 --reload
"""

from __future__ import annotations

import json
import asyncio
import logging
from typing import AsyncIterator, Dict, Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from drift_live_signal import LiveSignalStream, SignalSnapshot

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App + stream registry
# ---------------------------------------------------------------------------

app = FastAPI(title="drift_orchestrator live signal API", version="2.0.0")

# session_id -> LiveSignalStream
_registry: Dict[str, LiveSignalStream] = {}
_DEFAULT = "default"


def _get_stream(session_id: str = _DEFAULT) -> LiveSignalStream:
    """Return existing stream or create one for this session."""
    if session_id not in _registry:
        _registry[session_id] = LiveSignalStream(
            session_id=session_id, queue_maxsize=128
        )
    return _registry[session_id]


def register_stream(stream: LiveSignalStream) -> None:
    """
    Called by AgentRuntime (or any producer) to register its own
    LiveSignalStream instance so the API exposes it directly.

        from live_signal_api import register_stream
        register_stream(self.telemetry)
    """
    _registry[stream._session_id] = stream


# Ensure default stream exists at startup
_get_stream(_DEFAULT)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ScoreUpdate(BaseModel):
    alpha: float = Field(..., ge=0.0, le=1.0)
    external: float = Field(..., ge=0.0, le=1.0)
    session_id: Optional[str] = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "sessions": list(_registry.keys()),
        "total_subscribers": sum(s.subscriber_count for s in _registry.values()),
    }


@app.get("/sessions")
async def sessions() -> dict:
    return {
        sid: {
            "seq": s.seq,
            "subscribers": s.subscriber_count,
            "has_data": s.last_snapshot is not None,
        }
        for sid, s in _registry.items()
    }


@app.post("/register/{session_id}")
async def register(session_id: str) -> JSONResponse:
    """Explicitly create/touch a session stream entry."""
    _get_stream(session_id)
    return JSONResponse({"registered": session_id})


@app.get("/snapshot")
async def snapshot_default() -> JSONResponse:
    return _snapshot_response(_DEFAULT)


@app.get("/snapshot/{session_id}")
async def snapshot_session(session_id: str) -> JSONResponse:
    return _snapshot_response(session_id)


def _snapshot_response(session_id: str) -> JSONResponse:
    stream = _registry.get(session_id)
    if stream is None:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} not found")
    snap = stream.last_snapshot
    if snap is None:
        return JSONResponse({"error": "no snapshot yet"}, status_code=204)
    return JSONResponse(snap.as_dict())


@app.post("/score")
async def push_score(update: ScoreUpdate) -> JSONResponse:
    sid = update.session_id or _DEFAULT
    stream = _get_stream(sid)
    snap = await stream.update_scores(update.alpha, update.external)
    if snap is None:
        return JSONResponse({"status": "no_change"})
    return JSONResponse({"status": "emitted", "seq": snap.seq, "snapshot": snap.as_dict()})


@app.get("/stream")
async def sse_stream_default(request: Request) -> StreamingResponse:
    return _sse_response(request, _DEFAULT)


@app.get("/stream/{session_id}")
async def sse_stream_session(session_id: str, request: Request) -> StreamingResponse:
    if session_id not in _registry:
        _get_stream(session_id)
    return _sse_response(request, session_id)


def _sse_response(request: Request, session_id: str) -> StreamingResponse:
    return StreamingResponse(
        _sse_generator(request, session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


async def _sse_generator(request: Request, session_id: str) -> AsyncIterator[str]:
    stream = _get_stream(session_id)
    q = await stream.subscribe()
    try:
        while True:
            if await request.is_disconnected():
                break
            try:
                snapshot: SignalSnapshot = await asyncio.wait_for(q.get(), timeout=15.0)
                payload = json.dumps(snapshot.as_dict())
                yield f"data: {payload}\n\n"
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        await stream.unsubscribe(q)


# ---------------------------------------------------------------------------
# Dev entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("live_signal_api:app", host="0.0.0.0", port=8765, reload=True)
