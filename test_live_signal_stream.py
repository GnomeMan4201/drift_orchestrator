"""
test_live_signal_stream.py
==========================
Async pytest suite for drift_live_signal.LiveSignalStream.

Run:
    python -m pytest test_live_signal_stream.py -v
"""

from __future__ import annotations

import asyncio
import time

import pytest

from drift_live_signal import LiveSignalStream, PolicyAction, SignalSnapshot

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _drain(q: asyncio.Queue, timeout: float = 0.1) -> list[SignalSnapshot]:
    """Collect all immediately available items from a queue."""
    items = []
    try:
        while True:
            items.append(q.get_nowait())
    except asyncio.QueueEmpty:
        pass
    return items


# ---------------------------------------------------------------------------
# Delta emission semantics
# ---------------------------------------------------------------------------

class TestDeltaEmission:
    """Only changed state should produce a snapshot."""

    @pytest.mark.asyncio
    async def test_first_update_emits(self):
        s = LiveSignalStream()
        snap = await s.update_scores(0.1, 0.1)
        assert snap is not None
        assert snap.seq == 1

    @pytest.mark.asyncio
    async def test_identical_update_no_emit(self):
        s = LiveSignalStream()
        await s.update_scores(0.1, 0.1)
        snap2 = await s.update_scores(0.1, 0.1)
        assert snap2 is None

    @pytest.mark.asyncio
    async def test_changed_alpha_emits(self):
        s = LiveSignalStream()
        await s.update_scores(0.1, 0.1)
        snap = await s.update_scores(0.2, 0.1)
        assert snap is not None
        assert snap.seq == 2
        assert snap.alpha == pytest.approx(0.2)

    @pytest.mark.asyncio
    async def test_seq_increments_on_each_emission(self):
        s = LiveSignalStream()
        snaps = []
        for v in [0.1, 0.2, 0.3]:
            snap = await s.update_internal_score(v)
            if snap:
                snaps.append(snap)
        seqs = [sn.seq for sn in snaps]
        assert seqs == list(range(1, len(snaps) + 1))

    @pytest.mark.asyncio
    async def test_no_emit_before_any_update(self):
        s = LiveSignalStream()
        assert s.last_snapshot is None


# ---------------------------------------------------------------------------
# Divergence correctness
# ---------------------------------------------------------------------------

class TestDivergence:

    @pytest.mark.asyncio
    async def test_divergence_is_abs_diff(self):
        s = LiveSignalStream()
        snap = await s.update_scores(alpha=0.8, external=0.3)
        assert snap is not None
        assert snap.divergence == pytest.approx(abs(0.8 - 0.3))

    @pytest.mark.asyncio
    async def test_zero_divergence_when_equal(self):
        s = LiveSignalStream()
        snap = await s.update_scores(0.5, 0.5)
        assert snap.divergence == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_divergence_direction_agnostic(self):
        s1 = LiveSignalStream()
        s2 = LiveSignalStream()
        snap1 = await s1.update_scores(0.3, 0.7)
        snap2 = await s2.update_scores(0.7, 0.3)
        assert snap1.divergence == pytest.approx(snap2.divergence)

    @pytest.mark.asyncio
    async def test_high_divergence_stored_in_snapshot(self):
        s = LiveSignalStream()
        snap = await s.update_scores(0.0, 1.0)
        assert snap.divergence == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Policy transitions
# ---------------------------------------------------------------------------

class TestPolicyTransitions:

    @pytest.mark.asyncio
    async def test_low_alpha_low_div_continue(self):
        s = LiveSignalStream()
        snap = await s.update_scores(0.1, 0.1)
        assert snap.policy_action == PolicyAction.CONTINUE

    @pytest.mark.asyncio
    async def test_high_alpha_rollback(self):
        s = LiveSignalStream()
        snap = await s.update_scores(0.8, 0.1)
        assert snap.policy_action == PolicyAction.ROLLBACK

    @pytest.mark.asyncio
    async def test_warn_alpha_inject(self):
        s = LiveSignalStream()
        snap = await s.update_scores(0.6, 0.1)
        assert snap.policy_action == PolicyAction.INJECT

    @pytest.mark.asyncio
    async def test_high_divergence_rollback(self):
        s = LiveSignalStream()
        # divergence = 0.65 >= 0.60 threshold
        snap = await s.update_scores(0.1, 0.75)
        assert snap.divergence >= 0.60
        assert snap.policy_action == PolicyAction.ROLLBACK

    @pytest.mark.asyncio
    async def test_divergence_streak_triggers_rollback(self):
        """Five consecutive warn-level divergence events → ROLLBACK."""
        s = LiveSignalStream()
        last = None
        # div ~0.45 > _DIV_WARN(0.40), < _DIV_RB(0.60)
        for i in range(6):
            # vary alpha slightly so each update is a new state
            snap = await s.update_scores(0.05 + i * 0.001, 0.5 + i * 0.001)
            if snap is not None:
                last = snap
        assert last is not None
        assert last.policy_action == PolicyAction.ROLLBACK

    @pytest.mark.asyncio
    async def test_inject_escalates_to_regenerate(self):
        """Sustained warn-zone alpha after INJECT → REGENERATE."""
        s = LiveSignalStream()
        # First hit: INJECT
        snap1 = await s.update_scores(0.6, 0.1)
        assert snap1.policy_action == PolicyAction.INJECT
        # Second hit at same level: REGENERATE
        snap2 = await s.update_scores(0.61, 0.1)
        assert snap2 is not None
        assert snap2.policy_action == PolicyAction.REGENERATE

    @pytest.mark.asyncio
    async def test_policy_action_in_snapshot(self):
        s = LiveSignalStream()
        snap = await s.update_scores(0.2, 0.2)
        assert snap.policy_action in {
            PolicyAction.CONTINUE,
            PolicyAction.INJECT,
            PolicyAction.REGENERATE,
            PolicyAction.ROLLBACK,
        }


# ---------------------------------------------------------------------------
# Queue ordering
# ---------------------------------------------------------------------------

class TestQueueOrdering:

    @pytest.mark.asyncio
    async def test_subscriber_receives_snapshots_in_order(self):
        s = LiveSignalStream()
        q = await s.subscribe()
        scores = [(0.1, 0.1), (0.2, 0.1), (0.3, 0.1)]
        for alpha, ext in scores:
            await s.update_scores(alpha, ext)

        received = await _drain(q)
        await s.unsubscribe(q)

        seqs = [sn.seq for sn in received]
        assert seqs == sorted(seqs), "snapshots must arrive in seq order"
        assert seqs[0] == 1

    @pytest.mark.asyncio
    async def test_initial_snapshot_sent_on_subscribe(self):
        s = LiveSignalStream()
        await s.update_scores(0.3, 0.1)  # create a snapshot first
        q = await s.subscribe()
        received = await _drain(q)
        await s.unsubscribe(q)
        assert len(received) >= 1
        assert received[0].seq == 1

    @pytest.mark.asyncio
    async def test_multiple_subscribers_each_get_all(self):
        s = LiveSignalStream()
        q1 = await s.subscribe()
        q2 = await s.subscribe()
        await s.update_scores(0.2, 0.1)
        await s.update_scores(0.3, 0.1)

        r1 = await _drain(q1)
        r2 = await _drain(q2)
        await s.unsubscribe(q1)
        await s.unsubscribe(q2)

        assert len(r1) == len(r2)
        assert [sn.seq for sn in r1] == [sn.seq for sn in r2]

    @pytest.mark.asyncio
    async def test_unsubscribe_stops_delivery(self):
        s = LiveSignalStream()
        q = await s.subscribe()
        await s.update_scores(0.1, 0.1)
        await s.unsubscribe(q)
        await s.update_scores(0.2, 0.1)
        received_after = await _drain(q)
        # The queue may hold the first snapshot but not the second
        assert all(sn.seq <= 1 for sn in received_after)


# ---------------------------------------------------------------------------
# Async evaluator (non-blocking behaviour)
# ---------------------------------------------------------------------------

class TestAsyncEvaluator:

    @pytest.mark.asyncio
    async def test_evaluate_external_async_updates_score(self):
        s = LiveSignalStream()

        async def fake_evaluator(x: float) -> float:
            await asyncio.sleep(0)  # yield
            return x * 0.5

        snap = await s.evaluate_external_async(fake_evaluator, 0.6)
        assert snap is not None
        assert snap.external == pytest.approx(0.3)

    @pytest.mark.asyncio
    async def test_evaluator_does_not_block_other_updates(self):
        """Evaluator runs outside the lock; a concurrent update must not deadlock."""
        s = LiveSignalStream()

        async def slow_evaluator() -> float:
            await asyncio.sleep(0.01)
            return 0.4

        t0 = time.monotonic()
        # Run evaluator and an internal update concurrently
        snap_ext, snap_int = await asyncio.gather(
            s.evaluate_external_async(slow_evaluator),
            s.update_internal_score(0.5),
        )
        elapsed = time.monotonic() - t0
        # Both should complete in roughly evaluator delay, not 2×
        assert elapsed < 0.5
        # At least one snapshot must have been produced
        assert snap_ext is not None or snap_int is not None

    @pytest.mark.asyncio
    async def test_stream_async_generator(self):
        """stream() yields a snapshot when one is available."""
        s = LiveSignalStream()
        await s.update_scores(0.1, 0.1)

        gen = s.stream()
        snap = await asyncio.wait_for(gen.__anext__(), timeout=1.0)
        await gen.aclose()
        assert snap.seq == 1


# ---------------------------------------------------------------------------
# Snapshot fields
# ---------------------------------------------------------------------------

class TestSnapshotFields:

    @pytest.mark.asyncio
    async def test_snapshot_has_all_expected_fields(self):
        s = LiveSignalStream(session_id="test-session")
        snap = await s.update_scores(0.4, 0.3)
        d = snap.as_dict()
        for key in ("seq", "ts", "alpha", "external", "divergence", "policy_action", "reason", "session_id"):
            assert key in d, f"missing key: {key}"

    @pytest.mark.asyncio
    async def test_session_id_propagated(self):
        s = LiveSignalStream(session_id="abc-123")
        snap = await s.update_scores(0.1, 0.1)
        assert snap.session_id == "abc-123"

    @pytest.mark.asyncio
    async def test_timestamp_is_recent(self):
        s = LiveSignalStream()
        t0 = time.time()
        snap = await s.update_scores(0.1, 0.1)
        assert snap.ts >= t0
        assert snap.ts <= time.time() + 1.0
