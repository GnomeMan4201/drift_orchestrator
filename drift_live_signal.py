"""
drift_live_signal.py
====================
Async-safe live telemetry signal stream for drift_orchestrator.

Provides:
  - LiveSignalStream  — bounded async queue, delta emission, divergence,
                        policy transitions, multi-subscriber fan-out
  - PolicyAction      — typed constants matching policy.py conventions

No HTTP or TUI concerns live here.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field, asdict
from typing import AsyncIterator, Dict, List, Optional, Set

# ---------------------------------------------------------------------------
# Policy action constants (mirror policy.py; no import coupling)
# ---------------------------------------------------------------------------

class PolicyAction:
    CONTINUE   = "CONTINUE"
    INJECT     = "INJECT"
    REGENERATE = "REGENERATE"
    ROLLBACK   = "ROLLBACK"

    _RANK: Dict[str, int] = {
        "CONTINUE":   0,
        "INJECT":     1,
        "REGENERATE": 2,
        "ROLLBACK":   3,
    }

    @classmethod
    def rank(cls, action: str) -> int:
        return cls._RANK.get(action, 0)


# ---------------------------------------------------------------------------
# Thresholds — kept local so the stream layer is self-contained
# ---------------------------------------------------------------------------

_DIV_WARN = 0.40
_DIV_RB   = 0.60
_DIV_STREAK_RB = 5


# ---------------------------------------------------------------------------
# Snapshot dataclass — what subscribers receive
# ---------------------------------------------------------------------------

@dataclass
class SignalSnapshot:
    seq: int
    ts: float
    alpha: float
    external: float
    divergence: float
    policy_action: str
    reason: str
    session_id: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# LiveSignalStream
# ---------------------------------------------------------------------------

class LiveSignalStream:
    """
    Async-safe stream of SignalSnapshots.

    Scores are updated independently via update_internal_score() /
    update_external_score(). A snapshot is emitted only when the derived
    state actually changes (delta semantics).

    Fan-out: each subscriber gets its own bounded asyncio.Queue so one
    slow consumer cannot block others.

    Policy transitions are computed inline — no dependency on policy.py
    so the stream layer stays portable and testable in isolation.
    """

    def __init__(
        self,
        session_id: str = "",
        queue_maxsize: int = 64,
    ) -> None:
        self._session_id = session_id
        self._queue_maxsize = queue_maxsize

        # mutable state (protected by _lock)
        self._lock = asyncio.Lock()
        self._seq: int = 0
        self._alpha: float = 0.0
        self._external: float = 0.0
        self._divergence: float = 0.0
        self._policy_action: str = PolicyAction.CONTINUE
        self._reason: str = "initialised"
        self._div_streak: int = 0
        self._last_snapshot: Optional[SignalSnapshot] = None

        # subscriber queues
        self._subscribers: Set[asyncio.Queue] = set()

    # ------------------------------------------------------------------
    # Score update API
    # ------------------------------------------------------------------

    async def update_internal_score(self, alpha: float) -> Optional[SignalSnapshot]:
        """Update the internal (alpha) drift score. Emits if state changed."""
        async with self._lock:
            self._alpha = float(alpha)
            return await self._maybe_emit()

    async def update_external_score(self, external: float) -> Optional[SignalSnapshot]:
        """Update the external evaluator score. Emits if state changed."""
        async with self._lock:
            self._external = float(external)
            return await self._maybe_emit()

    async def update_scores(
        self, alpha: float, external: float
    ) -> Optional[SignalSnapshot]:
        """Atomic dual-score update."""
        async with self._lock:
            self._alpha = float(alpha)
            self._external = float(external)
            return await self._maybe_emit()

    # ------------------------------------------------------------------
    # External async evaluator shim (non-blocking)
    # ------------------------------------------------------------------

    async def evaluate_external_async(
        self,
        evaluator_coro,
        *args,
        **kwargs,
    ) -> Optional[SignalSnapshot]:
        """
        Run an async evaluator coroutine without blocking the stream lock.
        The evaluator runs outside the lock; only the score update acquires it.
        """
        score = await evaluator_coro(*args, **kwargs)
        return await self.update_external_score(float(score))

    # ------------------------------------------------------------------
    # Subscription / streaming
    # ------------------------------------------------------------------

    async def subscribe(self) -> asyncio.Queue:
        """
        Return a per-subscriber asyncio.Queue.
        The caller must call unsubscribe() when done.
        Sends an initial snapshot immediately if one exists.
        """
        q: asyncio.Queue = asyncio.Queue(maxsize=self._queue_maxsize)
        async with self._lock:
            self._subscribers.add(q)
            snapshot = self._last_snapshot
        if snapshot is not None:
            await q.put(snapshot)
        return q

    async def unsubscribe(self, q: asyncio.Queue) -> None:
        async with self._lock:
            self._subscribers.discard(q)

    async def stream(self) -> AsyncIterator[SignalSnapshot]:
        """
        Async generator — yields snapshots as they arrive.
        Cleans up subscription on exit (including generator.aclose()).
        """
        q = await self.subscribe()
        try:
            while True:
                snapshot = await q.get()
                yield snapshot
        finally:
            await self.unsubscribe(q)

    # ------------------------------------------------------------------
    # Internal helpers (must be called with _lock held)
    # ------------------------------------------------------------------

    async def _maybe_emit(self) -> Optional[SignalSnapshot]:
        """Compute new state; emit only if something changed."""
        divergence = abs(self._alpha - self._external)
        action, reason = self._compute_policy(divergence)

        prev = self._last_snapshot
        if (
            prev is not None
            and prev.alpha == self._alpha
            and prev.external == self._external
            and prev.divergence == divergence
            and prev.policy_action == action
        ):
            return None  # delta check — nothing changed

        self._seq += 1
        self._divergence = divergence
        self._policy_action = action
        self._reason = reason

        snapshot = SignalSnapshot(
            seq=self._seq,
            ts=time.time(),
            alpha=self._alpha,
            external=self._external,
            divergence=divergence,
            policy_action=action,
            reason=reason,
            session_id=self._session_id,
        )
        self._last_snapshot = snapshot
        await self._fan_out(snapshot)
        return snapshot

    def _compute_policy(self, divergence: float) -> tuple[str, str]:
        """
        Stateless policy transition based on divergence.
        Returns (action, reason).
        """
        prev_action = self._policy_action

        # Hard divergence rollback
        if divergence >= _DIV_RB:
            self._div_streak += 1
            return (
                PolicyAction.ROLLBACK,
                f"divergence {divergence:.4f} >= threshold {_DIV_RB}",
            )

        if divergence >= _DIV_WARN:
            self._div_streak += 1
        else:
            self._div_streak = 0

        if self._div_streak >= _DIV_STREAK_RB:
            return (
                PolicyAction.ROLLBACK,
                f"divergence streak {self._div_streak} >= {_DIV_STREAK_RB}",
            )

        # Alpha-based policy (mirrors policy.py thresholds)
        alpha = self._alpha
        if alpha >= 0.75:
            action = PolicyAction.ROLLBACK
            reason = f"alpha {alpha:.4f} >= 0.75 rollback threshold"
        elif alpha >= 0.55:
            if prev_action == PolicyAction.INJECT:
                action = PolicyAction.REGENERATE
                reason = f"alpha {alpha:.4f} warn zone, escalating from INJECT"
            elif prev_action == PolicyAction.REGENERATE:
                action = PolicyAction.ROLLBACK
                reason = f"alpha {alpha:.4f} warn zone, escalating from REGENERATE"
            else:
                action = PolicyAction.INJECT
                reason = f"alpha {alpha:.4f} >= 0.55 warn threshold"
        elif alpha >= 0.45 and prev_action != PolicyAction.CONTINUE:
            action = prev_action  # hold
            reason = f"alpha {alpha:.4f} in hold band, maintaining {prev_action}"
        else:
            action = PolicyAction.CONTINUE
            reason = f"alpha {alpha:.4f} nominal"

        # Divergence pressure can upgrade to INJECT
        if (
            action == PolicyAction.CONTINUE
            and self._div_streak >= 2
            and divergence >= _DIV_WARN
        ):
            action = PolicyAction.INJECT
            reason = f"divergence pressure: streak={self._div_streak}, div={divergence:.4f}"

        return action, reason

    async def _fan_out(self, snapshot: SignalSnapshot) -> None:
        """
        Deliver snapshot to all subscriber queues.
        Drops (nowait) if a queue is full — backpressure: slow consumers
        are skipped rather than blocking the producer.
        """
        dead: List[asyncio.Queue] = []
        for q in self._subscribers:
            try:
                q.put_nowait(snapshot)
            except asyncio.QueueFull:
                # slow consumer: drop, do not block
                dead.append(q)
        for q in dead:
            self._subscribers.discard(q)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def last_snapshot(self) -> Optional[SignalSnapshot]:
        return self._last_snapshot

    @property
    def seq(self) -> int:
        return self._seq

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)
