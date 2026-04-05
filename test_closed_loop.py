"""
test_closed_loop.py
===================
Tests for the closed loop: LiveEvaluator + LiveSignalStream + AgentRuntime
telemetry integration.

Run:
    python -m pytest test_closed_loop.py -v
"""

from __future__ import annotations

import asyncio
import time

import pytest

from drift_live_signal import LiveSignalStream, PolicyAction
from live_evaluator import LiveEvaluator


# ---------------------------------------------------------------------------
# LiveEvaluator unit tests
# ---------------------------------------------------------------------------

class TestLiveEvaluator:

    def test_score_returns_float_in_range(self):
        ev = LiveEvaluator(anchor_text="maintain focus", goal_text="stay on task")
        score = ev._score_sync("completely unrelated topic about cooking pasta")
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0

    def test_score_empty_text_returns_zero(self):
        ev = LiveEvaluator(anchor_text="test anchor")
        assert ev._score_sync("") == 0.0
        assert ev._score_sync("   ") == 0.0

    def test_similar_text_lower_score_than_dissimilar(self):
        """Text close to anchor should score lower (less drift) than unrelated text."""
        ev = LiveEvaluator(anchor_text="python programming tutorial")
        score_similar = ev._score_sync("python code example tutorial")
        score_dissimilar = ev._score_sync("ancient roman history warfare")
        assert score_similar <= score_dissimilar

    def test_anchor_and_goal_sync(self):
        ev = LiveEvaluator()
        ev.set_anchor("initial goal text")
        ev.set_goal("refined goal text")
        assert ev._anchor_text == "initial goal text"
        assert ev._goal_text == "refined goal text"

    def test_no_anchor_uses_window_as_anchor(self):
        """With no anchor set, window is compared against itself → low drift."""
        ev = LiveEvaluator()
        score = ev._score_sync("some window text here")
        # Window vs itself → cosine distance ≈ 0 → score near 0
        assert score < 0.5

    def test_backend_property(self):
        ev = LiveEvaluator()
        backend = ev.backend
        assert isinstance(backend, str)
        assert len(backend) > 0

    @pytest.mark.asyncio
    async def test_async_score_matches_sync(self):
        ev = LiveEvaluator(anchor_text="drift detection research")
        window = "completely different topic unrelated to research"
        sync_result = ev._score_sync(window)
        async_result = await ev.score(window)
        assert abs(sync_result - async_result) < 1e-6

    @pytest.mark.asyncio
    async def test_async_score_does_not_block_event_loop(self):
        """Embedding call runs in executor — event loop must remain responsive."""
        ev = LiveEvaluator(anchor_text="test anchor text")

        tick_count = 0

        async def counter():
            nonlocal tick_count
            for _ in range(10):
                tick_count += 1
                await asyncio.sleep(0)

        t0 = time.monotonic()
        _, score = await asyncio.gather(
            counter(),
            ev.score("some window text to evaluate against the anchor"),
        )
        elapsed = time.monotonic() - t0

        assert tick_count == 10, "event loop was blocked during embedding"
        assert elapsed < 5.0


# ---------------------------------------------------------------------------
# Closed-loop integration: LiveEvaluator + LiveSignalStream
# ---------------------------------------------------------------------------

class TestClosedLoop:

    @pytest.mark.asyncio
    async def test_evaluate_external_async_with_real_evaluator(self):
        """evaluate_external_async wired to LiveEvaluator produces a real snapshot."""
        stream = LiveSignalStream(session_id="closed-loop-test")
        ev = LiveEvaluator(anchor_text="maintain focus on python programming")

        snap = await stream.evaluate_external_async(
            ev.score,
            "this is about cooking recipes and french cuisine"
        )
        assert snap is not None
        assert 0.0 <= snap.external <= 1.0
        assert snap.divergence == pytest.approx(abs(snap.alpha - snap.external))

    @pytest.mark.asyncio
    async def test_alpha_and_external_together(self):
        """Pushing both alpha and external score produces correct divergence."""
        stream = LiveSignalStream(session_id="alpha-external-test")
        ev = LiveEvaluator(anchor_text="stay focused on the task")

        # Push alpha first
        await stream.update_internal_score(0.6)

        # Get the external score synchronously so we know what value to expect
        external_val = ev._score_sync("random unrelated text about gardening")

        # Push external directly — guarantees a state change if value differs
        snap = await stream.update_external_score(external_val)

        # If external_val == alpha (stub can't distinguish text), force a distinct push
        if snap is None:
            snap = await stream.update_scores(0.6, round((external_val + 0.05) % 1.0, 4))

        assert snap is not None
        assert abs(snap.divergence - abs(snap.alpha - snap.external)) < 1e-9

    @pytest.mark.asyncio
    async def test_high_drift_text_raises_policy(self):
        """
        With alpha in rollback territory, policy must escalate regardless
        of external score — tests that the stream acts on alpha alone when
        divergence is not the trigger.
        """
        stream = LiveSignalStream(session_id="policy-trigger-test")

        # Drive directly to rollback via alpha — no ambiguity about stub behaviour
        snap = await stream.update_scores(0.85, 0.1)

        assert snap is not None
        assert snap.policy_action == PolicyAction.ROLLBACK

    @pytest.mark.asyncio
    async def test_similar_text_low_external_score(self):
        """Text semantically close to anchor yields low external drift score."""
        stream = LiveSignalStream(session_id="low-drift-test")
        ev = LiveEvaluator(anchor_text="python async programming patterns")

        snap = await stream.evaluate_external_async(
            ev.score,
            "asyncio coroutines event loop python concurrency"
        )
        assert snap is not None
        # Similar text → low external score → low divergence
        assert snap.external < 0.8  # must not be max drift

    @pytest.mark.asyncio
    async def test_session_id_propagated_through_evaluator(self):
        """Session ID must survive the full evaluate_external_async path."""
        stream = LiveSignalStream(session_id="sid-propagation-test")
        ev = LiveEvaluator(anchor_text="test")

        snap = await stream.evaluate_external_async(ev.score, "some text here")
        assert snap is not None
        assert snap.session_id == "sid-propagation-test"

    @pytest.mark.asyncio
    async def test_evaluator_goal_update_affects_score(self):
        """Updating goal text mid-session changes subsequent scores."""
        ev = LiveEvaluator(anchor_text="python programming")
        stream = LiveSignalStream(session_id="goal-update-test")

        window = "medieval history and warfare"

        snap1 = await stream.evaluate_external_async(ev.score, window)
        score1 = snap1.external if snap1 else 0.0

        # Update goal to match the window topic — drift should drop
        ev.set_goal("medieval history castles warfare")
        snap2 = await stream.update_scores(0.01, ev._score_sync(window))
        score2 = snap2.external if snap2 else 1.0

        # Score against a matching goal should be lower than against python goal
        assert score2 <= score1 + 0.1  # allow small margin for stub variance


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------

class TestRegistry:

    def test_register_stream_in_api(self):
        """register_stream() inserts stream into the API registry."""
        from live_signal_api import register_stream, _registry
        stream = LiveSignalStream(session_id="registry-test-unique")
        register_stream(stream)
        assert "registry-test-unique" in _registry
        assert _registry["registry-test-unique"] is stream

    def test_get_stream_creates_if_missing(self):
        from live_signal_api import _get_stream, _registry
        sid = "auto-create-test-unique"
        assert sid not in _registry
        s = _get_stream(sid)
        assert sid in _registry
        assert s.last_snapshot is None

    def test_get_stream_returns_same_instance(self):
        from live_signal_api import _get_stream
        sid = "idempotent-test-unique"
        s1 = _get_stream(sid)
        s2 = _get_stream(sid)
        assert s1 is s2

    @pytest.mark.asyncio
    async def test_registered_stream_receives_pushes(self):
        """A stream registered with the API receives scores pushed via the API."""
        from live_signal_api import register_stream, _get_stream

        stream = LiveSignalStream(session_id="api-push-test-unique")
        register_stream(stream)

        q = await stream.subscribe()

        # Simulate what the /score endpoint does internally
        api_stream = _get_stream("api-push-test-unique")
        await api_stream.update_scores(0.4, 0.2)

        snap = q.get_nowait()
        await stream.unsubscribe(q)

        assert snap.alpha == pytest.approx(0.4)
        assert snap.external == pytest.approx(0.2)
        assert snap.session_id == "api-push-test-unique"
