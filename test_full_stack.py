"""
test_full_stack.py
==================
Full stack tests for the live telemetry system.

A — Integration:   LiveSignalStream wired into AgentRuntime-style score loop
B — Stress:        concurrent subscribers, rapid pushes, backpressure
C — Scenario:      scripted CONTINUE→INJECT→REGENERATE→ROLLBACK walk
D — Multi-stream:  two independent streams, divergent score sequences

Run:
    python -m pytest test_full_stack.py -v
"""

from __future__ import annotations

import asyncio
import time
import threading
from typing import List

import pytest

from drift_live_signal import LiveSignalStream, PolicyAction, SignalSnapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _collect(stream: LiveSignalStream, n: int, timeout: float = 5.0) -> List[SignalSnapshot]:
    """Collect exactly n snapshots from a fresh subscriber."""
    q = await stream.subscribe()
    results = []
    deadline = time.monotonic() + timeout
    try:
        while len(results) < n:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                snap = await asyncio.wait_for(q.get(), timeout=remaining)
                results.append(snap)
            except asyncio.TimeoutError:
                break
    finally:
        await stream.unsubscribe(q)
    return results


def _simulate_alpha(turn: int) -> float:
    """Synthetic alpha curve: rises through warn zone then spikes."""
    curve = [0.1, 0.15, 0.2, 0.3, 0.45, 0.55, 0.62, 0.70, 0.80, 0.85]
    return curve[min(turn, len(curve) - 1)]


# ===========================================================================
# A — Integration test
# Simulates AgentRuntime-style per-turn score emission into LiveSignalStream
# ===========================================================================

class TestIntegration:
    """
    Wire LiveSignalStream into a synthetic agent loop.
    Each 'turn' produces alpha + external scores, just as agent_runtime.py
    computes them. Verify the stream tracks the session correctly.
    """

    @pytest.mark.asyncio
    async def test_agent_loop_emits_per_turn(self):
        """Stream receives one snapshot per turn where state changed."""
        stream = LiveSignalStream(session_id="integration-test")

        # Simulate 10 turns with a rising alpha curve
        turns = 10
        emitted = []
        for t in range(turns):
            alpha = _simulate_alpha(t)
            external = alpha * 0.7  # external tracks alpha loosely
            snap = await stream.update_scores(alpha, external)
            if snap is not None:
                emitted.append(snap)

        # All snapshots must carry the session_id
        assert all(s.session_id == "integration-test" for s in emitted)
        # Seqs must be strictly monotonic
        seqs = [s.seq for s in emitted]
        assert seqs == sorted(seqs)
        assert seqs == list(range(1, len(seqs) + 1))
        # Must have emitted at least once
        assert len(emitted) >= 1

    @pytest.mark.asyncio
    async def test_alpha_curve_produces_escalating_policy(self):
        """Rising alpha through the curve must escalate policy action."""
        stream = LiveSignalStream(session_id="escalation-test")

        actions_seen = set()
        for t in range(10):
            alpha = _simulate_alpha(t)
            snap = await stream.update_scores(alpha, 0.05)
            if snap:
                actions_seen.add(snap.policy_action)

        # With alpha reaching 0.85, ROLLBACK must have been triggered
        assert PolicyAction.ROLLBACK in actions_seen
        # And INJECT must have appeared before it
        assert PolicyAction.INJECT in actions_seen

    @pytest.mark.asyncio
    async def test_external_score_tracks_divergence(self):
        """Divergence is correctly computed across a realistic turn sequence."""
        stream = LiveSignalStream(session_id="divergence-test")

        divergences = []
        alphas = [0.2, 0.4, 0.6, 0.8]
        externals = [0.1, 0.1, 0.1, 0.1]  # external stays low → divergence grows

        for a, e in zip(alphas, externals):
            snap = await stream.update_scores(a, e)
            if snap:
                divergences.append(snap.divergence)
                assert abs(snap.divergence - abs(a - e)) < 1e-9

        # Divergence must grow as alpha rises
        assert divergences == sorted(divergences)

    @pytest.mark.asyncio
    async def test_subscriber_sees_full_session_history(self):
        """A subscriber that joins mid-session gets the latest snapshot immediately."""
        stream = LiveSignalStream(session_id="history-test")

        # Push 5 turns before subscribing
        for t in range(5):
            await stream.update_scores(_simulate_alpha(t), 0.05)

        # Subscribe after the fact
        q = await stream.subscribe()
        initial = []
        try:
            while True:
                initial.append(q.get_nowait())
        except asyncio.QueueEmpty:
            pass
        await stream.unsubscribe(q)

        # Should get the latest snapshot as the initial event
        assert len(initial) == 1
        assert initial[0].seq == stream.seq

    @pytest.mark.asyncio
    async def test_no_duplicate_emit_on_identical_turn(self):
        """If two consecutive turns produce identical scores, only one snapshot emitted."""
        stream = LiveSignalStream(session_id="dedup-test")
        await stream.update_scores(0.3, 0.1)
        seq_before = stream.seq
        # Same scores again — should not emit
        result = await stream.update_scores(0.3, 0.1)
        assert result is None
        assert stream.seq == seq_before


# ===========================================================================
# B — Stress test
# Concurrent subscribers, rapid pushes, backpressure verification
# ===========================================================================

class TestStress:

    @pytest.mark.asyncio
    async def test_rapid_score_pushes_no_deadlock(self):
        """1000 rapid pushes must complete without hanging."""
        stream = LiveSignalStream()
        t0 = time.monotonic()
        for i in range(1000):
            await stream.update_scores(i / 1000.0, (i + 1) / 1000.0)
        elapsed = time.monotonic() - t0
        assert elapsed < 10.0, f"1000 pushes took {elapsed:.2f}s — possible deadlock"
        assert stream.seq <= 1000  # can't exceed push count

    @pytest.mark.asyncio
    async def test_concurrent_subscribers_all_receive(self):
        """10 concurrent subscribers all receive the same snapshots."""
        stream = LiveSignalStream()
        n_subs = 10
        n_events = 5

        queues = [await stream.subscribe() for _ in range(n_subs)]

        # Push n_events distinct score pairs
        for i in range(n_events):
            await stream.update_scores(0.1 * (i + 1), 0.05)

        # Drain all queues
        results = []
        for q in queues:
            items = []
            try:
                while True:
                    items.append(q.get_nowait())
            except asyncio.QueueEmpty:
                pass
            await stream.unsubscribe(q)
            results.append(items)

        # Every subscriber must have received the same seqs
        ref_seqs = [s.seq for s in results[0]]
        for i, r in enumerate(results[1:], 1):
            assert [s.seq for s in r] == ref_seqs, f"subscriber {i} got different seqs"

    @pytest.mark.asyncio
    async def test_backpressure_slow_consumer_dropped_not_blocked(self):
        """A full queue (maxsize=2) must not block the producer."""
        stream = LiveSignalStream(queue_maxsize=2)
        q = await stream.subscribe()

        # Don't drain the queue — fill it up then keep pushing
        t0 = time.monotonic()
        for i in range(20):
            await stream.update_scores(0.01 * i, 0.0)
        elapsed = time.monotonic() - t0

        await stream.unsubscribe(q)
        # Producer must not have blocked — 20 pushes should be near-instant
        assert elapsed < 2.0, f"backpressure blocked producer for {elapsed:.2f}s"

    @pytest.mark.asyncio
    async def test_concurrent_updates_no_race(self):
        """Concurrent alpha + external updates must not corrupt state."""
        stream = LiveSignalStream()

        async def push_alpha():
            for i in range(100):
                await stream.update_internal_score(i / 100.0)
                await asyncio.sleep(0)

        async def push_external():
            for i in range(100):
                await stream.update_external_score(i / 200.0)
                await asyncio.sleep(0)

        await asyncio.gather(push_alpha(), push_external())

        snap = stream.last_snapshot
        assert snap is not None
        # Divergence must equal abs(alpha - external) — no corruption
        assert abs(snap.divergence - abs(snap.alpha - snap.external)) < 1e-9

    @pytest.mark.asyncio
    async def test_high_subscriber_churn(self):
        """Subscribers subscribing and unsubscribing mid-stream must not crash."""
        stream = LiveSignalStream()

        async def churn():
            for _ in range(50):
                q = await stream.subscribe()
                await asyncio.sleep(0)
                await stream.unsubscribe(q)

        async def push():
            for i in range(50):
                await stream.update_scores(i / 50.0, 0.0)
                await asyncio.sleep(0)

        await asyncio.gather(churn(), push())
        # Just verifying no exception — subscriber count must be 0 after churn
        assert stream.subscriber_count == 0

    @pytest.mark.asyncio
    async def test_stress_seq_integrity(self):
        """Under load, seq must be strictly monotonic with no gaps."""
        stream = LiveSignalStream()
        q = await stream.subscribe()

        # Push 200 distinct updates
        for i in range(200):
            await stream.update_scores(i / 200.0, (i + 1) / 200.0)

        snaps = []
        try:
            while True:
                snaps.append(q.get_nowait())
        except asyncio.QueueEmpty:
            pass
        await stream.unsubscribe(q)

        seqs = [s.seq for s in snaps]
        assert seqs == sorted(seqs), "seqs out of order under load"
        assert seqs[0] == 1
        # No gaps
        assert seqs == list(range(1, len(seqs) + 1))


# ===========================================================================
# C — Scenario test
# Scripted full policy walk: CONTINUE → INJECT → REGENERATE → ROLLBACK
# ===========================================================================

class TestScenario:

    @pytest.mark.asyncio
    async def test_full_policy_walk_ordered(self):
        """
        Drive the stream through all four policy states in order.
        Each state must appear before the next in the snapshot sequence.
        """
        stream = LiveSignalStream()
        snapshots = []

        async def capture():
            async for snap in stream.stream():
                snapshots.append(snap)
                if snap.policy_action == PolicyAction.ROLLBACK:
                    break

        task = asyncio.create_task(capture())

        # CONTINUE — low alpha, low divergence
        await stream.update_scores(0.1, 0.05)
        await asyncio.sleep(0)

        # INJECT — alpha enters warn zone
        await stream.update_scores(0.6, 0.05)
        await asyncio.sleep(0)

        # REGENERATE — alpha stays in warn zone after INJECT
        await stream.update_scores(0.62, 0.05)
        await asyncio.sleep(0)

        # ROLLBACK — alpha spikes
        await stream.update_scores(0.85, 0.05)
        await asyncio.sleep(0)

        await asyncio.wait_for(task, timeout=3.0)

        actions = [s.policy_action for s in snapshots]
        assert PolicyAction.CONTINUE   in actions
        assert PolicyAction.INJECT     in actions
        assert PolicyAction.REGENERATE in actions
        assert PolicyAction.ROLLBACK   in actions

        # Order must be correct: CONTINUE before INJECT before REGENERATE before ROLLBACK
        idx = {a: actions.index(a) for a in [
            PolicyAction.CONTINUE,
            PolicyAction.INJECT,
            PolicyAction.REGENERATE,
            PolicyAction.ROLLBACK,
        ]}
        assert idx[PolicyAction.CONTINUE]   < idx[PolicyAction.INJECT]
        assert idx[PolicyAction.INJECT]     < idx[PolicyAction.REGENERATE]
        assert idx[PolicyAction.REGENERATE] < idx[PolicyAction.ROLLBACK]

    @pytest.mark.asyncio
    async def test_divergence_streak_scenario(self):
        """
        Sustained moderate divergence (below _DIV_RB) must accumulate streak
        and eventually trigger ROLLBACK via streak threshold.
        """
        stream = LiveSignalStream()
        snaps = []

        # Push 7 updates with div ~0.45 (above _DIV_WARN=0.40, below _DIV_RB=0.60)
        # Each must be a distinct state to actually emit
        for i in range(7):
            snap = await stream.update_scores(0.05 + i * 0.002, 0.5 + i * 0.002)
            if snap:
                snaps.append(snap)

        actions = [s.policy_action for s in snaps]
        assert PolicyAction.ROLLBACK in actions, \
            f"expected ROLLBACK from streak, got: {actions}"

    @pytest.mark.asyncio
    async def test_recovery_after_rollback(self):
        """After ROLLBACK, dropping alpha back to nominal produces CONTINUE."""
        stream = LiveSignalStream()

        # Trigger rollback
        await stream.update_scores(0.85, 0.1)
        assert stream.last_snapshot.policy_action == PolicyAction.ROLLBACK

        # Recover — low alpha, low divergence
        # Need a slightly different external to force re-evaluation
        snap = await stream.update_scores(0.1, 0.09)
        assert snap is not None
        assert snap.policy_action == PolicyAction.CONTINUE

    @pytest.mark.asyncio
    async def test_reason_field_matches_action(self):
        """reason field must contain semantically relevant text for each action."""
        stream = LiveSignalStream()

        snap_cont = await stream.update_scores(0.1, 0.1)
        assert "nominal" in snap_cont.reason or "0.1" in snap_cont.reason

        snap_inj = await stream.update_scores(0.6, 0.1)
        assert snap_inj.policy_action == PolicyAction.INJECT
        assert "0.55" in snap_inj.reason or "warn" in snap_inj.reason or "0.6" in snap_inj.reason

        snap_rb = await stream.update_scores(0.85, 0.1)
        assert snap_rb.policy_action == PolicyAction.ROLLBACK
        assert any(kw in snap_rb.reason for kw in ["rollback", "threshold", "divergence", "0.8"])

    @pytest.mark.asyncio
    async def test_snapshot_timestamps_monotonic(self):
        """Timestamps must be non-decreasing across a session."""
        stream = LiveSignalStream()
        snaps = []
        for i in range(10):
            snap = await stream.update_scores(i * 0.08, i * 0.04)
            if snap:
                snaps.append(snap)
        ts = [s.ts for s in snaps]
        assert ts == sorted(ts), "timestamps not monotonic"


# ===========================================================================
# D — Multi-stream test
# Two independent streams with divergent score sequences
# ===========================================================================

class TestMultiStream:

    @pytest.mark.asyncio
    async def test_two_streams_fully_independent(self):
        """Events on stream A must not appear on stream B and vice versa."""
        stream_a = LiveSignalStream(session_id="node-A")
        stream_b = LiveSignalStream(session_id="node-B")

        q_a = await stream_a.subscribe()
        q_b = await stream_b.subscribe()

        await stream_a.update_scores(0.8, 0.1)   # A → ROLLBACK territory
        await stream_b.update_scores(0.1, 0.05)  # B → CONTINUE

        snaps_a, snaps_b = [], []
        try:
            while True: snaps_a.append(q_a.get_nowait())
        except asyncio.QueueEmpty: pass
        try:
            while True: snaps_b.append(q_b.get_nowait())
        except asyncio.QueueEmpty: pass

        await stream_a.unsubscribe(q_a)
        await stream_b.unsubscribe(q_b)

        assert all(s.session_id == "node-A" for s in snaps_a)
        assert all(s.session_id == "node-B" for s in snaps_b)
        assert snaps_a[0].policy_action == PolicyAction.ROLLBACK
        assert snaps_b[0].policy_action == PolicyAction.CONTINUE

    @pytest.mark.asyncio
    async def test_two_streams_divergent_policies(self):
        """Two streams pushed to different alpha levels must land on different policies."""
        stream_1 = LiveSignalStream(session_id="high-drift")
        stream_2 = LiveSignalStream(session_id="nominal")

        # Stream 1: escalating toward rollback
        for alpha in [0.3, 0.5, 0.6, 0.75, 0.85]:
            await stream_1.update_scores(alpha, 0.05)

        # Stream 2: stays nominal
        for alpha in [0.1, 0.12, 0.11, 0.13, 0.10]:
            await stream_2.update_scores(alpha, 0.08)

        snap_1 = stream_1.last_snapshot
        snap_2 = stream_2.last_snapshot

        assert snap_1.policy_action == PolicyAction.ROLLBACK
        assert snap_2.policy_action == PolicyAction.CONTINUE
        assert snap_1.divergence > snap_2.divergence

    @pytest.mark.asyncio
    async def test_two_streams_independent_seq_counters(self):
        """Each stream maintains its own independent seq counter."""
        stream_a = LiveSignalStream(session_id="A")
        stream_b = LiveSignalStream(session_id="B")

        # Push 3 to A, 5 to B
        for i in range(1, 4):
            await stream_a.update_scores(i * 0.1, 0.0)
        for i in range(1, 6):
            await stream_b.update_scores(i * 0.1, 0.0)

        assert stream_a.seq == 3
        assert stream_b.seq == 5

    @pytest.mark.asyncio
    async def test_concurrent_streams_no_interference(self):
        """Pushing to both streams concurrently must not corrupt either."""
        stream_a = LiveSignalStream(session_id="concurrent-A")
        stream_b = LiveSignalStream(session_id="concurrent-B")

        async def push_a():
            for i in range(50):
                await stream_a.update_scores(i / 50.0, 0.1)
                await asyncio.sleep(0)

        async def push_b():
            for i in range(50):
                await stream_b.update_scores(0.9 - i / 50.0, 0.8)
                await asyncio.sleep(0)

        await asyncio.gather(push_a(), push_b())

        snap_a = stream_a.last_snapshot
        snap_b = stream_b.last_snapshot

        assert snap_a.session_id == "concurrent-A"
        assert snap_b.session_id == "concurrent-B"
        assert abs(snap_a.divergence - abs(snap_a.alpha - snap_a.external)) < 1e-9
        assert abs(snap_b.divergence - abs(snap_b.alpha - snap_b.external)) < 1e-9

    @pytest.mark.asyncio
    async def test_fan_out_across_both_streams(self):
        """Each stream fans out to its own subscribers only."""
        stream_a = LiveSignalStream(session_id="fan-A")
        stream_b = LiveSignalStream(session_id="fan-B")

        # 3 subscribers per stream
        qs_a = [await stream_a.subscribe() for _ in range(3)]
        qs_b = [await stream_b.subscribe() for _ in range(3)]

        await stream_a.update_scores(0.5, 0.1)
        await stream_b.update_scores(0.2, 0.1)

        for q in qs_a:
            items = []
            try:
                while True: items.append(q.get_nowait())
            except asyncio.QueueEmpty: pass
            await stream_a.unsubscribe(q)
            assert len(items) == 1
            assert items[0].session_id == "fan-A"

        for q in qs_b:
            items = []
            try:
                while True: items.append(q.get_nowait())
            except asyncio.QueueEmpty: pass
            await stream_b.unsubscribe(q)
            assert len(items) == 1
            assert items[0].session_id == "fan-B"
