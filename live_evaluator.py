"""
live_evaluator.py
=================
Async embedding-based external evaluator for LiveSignalStream.

Wraps embeddings.py (local sentence-transformers / stub fallback) to produce
a real external score from window text, suitable for passing to:

    await stream.evaluate_external_async(live_score, window_text, anchor_text)

No gateway required. No network calls. Works offline via stub fallback.

Score semantics
---------------
The external score is the mean of:
  - anchor_dist : cosine distance between window text and session anchor
  - goal_dist   : cosine distance between window text and goal text

Higher = more drifted from the original context, matching alpha semantics
so divergence = abs(alpha - external) is meaningful.

Usage
-----
    from live_evaluator import LiveEvaluator

    evaluator = LiveEvaluator(anchor_text="...", goal_text="...")
    stream = LiveSignalStream(session_id="my-session")

    # In a turn loop:
    snap = await stream.evaluate_external_async(
        evaluator.score, window_text
    )
"""

from __future__ import annotations

import asyncio
import math
from functools import lru_cache
from typing import Optional


class LiveEvaluator:
    """
    Async-compatible external evaluator backed by local embeddings.

    Thread-safe: embed() in embeddings.py uses its own lock.
    The score() coroutine runs the blocking embed calls in a thread executor
    so it does not block the asyncio event loop.
    """

    def __init__(
        self,
        anchor_text: str = "",
        goal_text: str = "",
    ) -> None:
        self._anchor_text = anchor_text
        self._goal_text = goal_text
        self._backend: Optional[str] = None

    def set_anchor(self, text: str) -> None:
        self._anchor_text = text

    def set_goal(self, text: str) -> None:
        self._goal_text = text

    @property
    def backend(self) -> str:
        if self._backend is None:
            try:
                from embeddings import get_backend
                self._backend = get_backend()
            except Exception:
                self._backend = "unavailable"
        return self._backend

    async def score(self, window_text: str) -> float:
        """
        Async entry point — runs blocking embed in executor.
        Returns a float in [0.0, 1.0] where higher = more drifted.
        """
        if not window_text or not window_text.strip():
            return 0.0

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._score_sync, window_text
        )

    def _score_sync(self, window_text: str) -> float:
        """Synchronous scoring — called from executor thread."""
        try:
            from embeddings import embed, cosine_similarity, clamp
        except ImportError:
            # embeddings.py not available — return neutral score
            return 0.0

        anchor = self._anchor_text or window_text
        goal = self._goal_text or anchor

        try:
            v_window = embed(window_text)
            v_anchor = embed(anchor)
            v_goal   = embed(goal)

            anchor_sim = cosine_similarity(v_window, v_anchor)
            goal_sim   = cosine_similarity(v_window, v_goal)

            anchor_dist = max(0.0, min(1.0, 1.0 - anchor_sim))
            goal_dist   = max(0.0, min(1.0, 1.0 - goal_sim))

            external_score = (anchor_dist + goal_dist) / 2.0
            return round(max(0.0, min(1.0, external_score)), 4)

        except Exception:
            return 0.0


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))
