import uuid
from datetime import datetime, timezone

TAU_WARN_HIGH = 0.55
TAU_WARN_LOW  = 0.45
TAU_RB_HIGH   = 0.75
TAU_RB_LOW    = 0.65
TAU_DIV_WARN  = 0.40
TAU_DIV_RB    = 0.60
DIV_STREAK_RB = 5
TAU_MONOTONIC_WINDOWS = 4

MIN_WINDOW_TURNS   = 2
STABLE_STREAK_VETO = 2
STABLE_DRIFT_TAU   = 0.40

ACTION_CONTINUE   = "CONTINUE"
ACTION_INJECT     = "INJECT"
ACTION_REGENERATE = "REGENERATE"
ACTION_ROLLBACK   = "ROLLBACK"

RED_FINDING_TYPES = {
    "invented_import", "invented_api", "invented_cli_flag", "missing_import",
    "injection_evaluator_override", "injection_forced_json_output",
    "injection_score_injection", "injection_evaluator_authority_spoof",
    "injection_prescore_claim",
}


class PolicyEngine:
    def __init__(self):
        self._state = ACTION_CONTINUE
        self._last_alpha = 0.0
        self._div_streak = 0
        self._anchor_history = []
        self._stable_streak = 0
        self._governor_active = False

    def evaluate(self, alpha, turn_index, session_id=None, branch_id=None,
                 findings=None, divergence=None, embed_score=None, d_anchor=None,
                 external_verdict=None, external_drift=None):
        prev = self._state

        has_red = any(
            f.get("type") in RED_FINDING_TYPES and f.get("severity") == "HIGH"
            for f in (findings or [])
        )
        if has_red:
            action = ACTION_ROLLBACK
            reason = f"hard override: RED findings detected at turn {turn_index}"
            return self._finalize(action, reason, alpha, turn_index, session_id, branch_id)

        action = self._decide(alpha, prev)
        reason = self._reason(alpha, prev, action)

        if action != ACTION_ROLLBACK and divergence is not None:
            if divergence >= TAU_DIV_WARN:
                self._div_streak += 1
            else:
                self._div_streak = 0
            if divergence >= TAU_DIV_RB:
                action = ACTION_ROLLBACK
                reason = "divergence override: div={:.4f} >= tau_div_rb={}".format(divergence, TAU_DIV_RB)
            elif self._div_streak >= DIV_STREAK_RB:
                action = ACTION_ROLLBACK
                reason = "divergence override: streak={} >= {}".format(self._div_streak, DIV_STREAK_RB)
            elif self._div_streak >= 2 and action == ACTION_CONTINUE:
                action = ACTION_INJECT
                reason = "divergence pressure: streak={}, div={:.4f}".format(self._div_streak, divergence)

        if (action not in (ACTION_CONTINUE, ACTION_ROLLBACK)
                and turn_index >= MIN_WINDOW_TURNS
                and external_verdict is not None
                and external_drift is not None):
            ext_is_stable = (external_verdict == "STABLE" and external_drift < STABLE_DRIFT_TAU)
            if ext_is_stable:
                self._stable_streak += 1
            else:
                self._stable_streak = 0
                self._governor_active = False
            if self._stable_streak >= STABLE_STREAK_VETO:
                prev_action = action
                action = ACTION_CONTINUE
                self._governor_active = True
                reason = (
                    "dual-signal governor: geometric={} suppressed by "
                    "external STABLE x{} (ext_drift={:.2f})".format(
                        prev_action, self._stable_streak, external_drift
                    )
                )
        elif external_verdict is not None:
            self._stable_streak = 0
            self._governor_active = False

        # ── Dual-signal escalation hold ───────────────────────────────────────
        # Streak is managed by governor block above for non-ROLLBACK actions.
        # For ROLLBACK (skipped by governor block), update streak here so hold
        # check can engage on current turn's verdict.
        if action == ACTION_ROLLBACK and external_verdict is not None:
            if external_verdict == "STABLE" and external_drift is not None and external_drift < STABLE_DRIFT_TAU:
                self._stable_streak += 1
            else:
                self._stable_streak = 0
                self._governor_active = False

        if (action == ACTION_ROLLBACK
                and self._stable_streak >= 1
                and turn_index >= MIN_WINDOW_TURNS
                and external_verdict == "STABLE"
                and external_drift is not None
                and external_drift < STABLE_DRIFT_TAU):
            action = ACTION_INJECT
            reason = "dual-signal governor: ROLLBACK held, external STABLE building (streak={})".format(
                self._stable_streak
            )

        if d_anchor is not None:
            self._anchor_history.append(d_anchor)
            if len(self._anchor_history) >= TAU_MONOTONIC_WINDOWS:
                w = self._anchor_history[-TAU_MONOTONIC_WINDOWS:]
                if all(w[i] <= w[i+1] for i in range(len(w)-1)):
                    action = ACTION_ROLLBACK
                    reason = "monotonic anchor drift: d_anchor increased {} consecutive windows ({})".format(
                        TAU_MONOTONIC_WINDOWS,
                        ", ".join("{:.4f}".format(x) for x in w)
                    )

        return self._finalize(action, reason, alpha, turn_index, session_id, branch_id)

    def _finalize(self, action, reason, alpha, turn_index, session_id, branch_id):
        self._state = action
        self._last_alpha = alpha
        level = self._level(action)
        event = {
            "id": str(uuid.uuid4()),
            "session_id": session_id or "",
            "branch_id": branch_id or "",
            "turn_index": turn_index,
            "alpha": alpha,
            "action": action,
            "reason": reason,
            "level": level,
            "governor_active": self._governor_active,
            "stable_streak": self._stable_streak,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        return action, level, reason, event

    def _decide(self, alpha, prev_state):
        if alpha >= TAU_RB_HIGH:
            return ACTION_ROLLBACK
        if alpha >= TAU_WARN_HIGH:
            if prev_state == ACTION_INJECT:
                return ACTION_REGENERATE
            if prev_state == ACTION_REGENERATE:
                return ACTION_ROLLBACK
            return ACTION_INJECT
        if alpha >= TAU_WARN_LOW and prev_state != ACTION_CONTINUE:
            return prev_state
        return ACTION_CONTINUE

    def _level(self, action):
        return {ACTION_CONTINUE: 0, ACTION_INJECT: 1, ACTION_REGENERATE: 2, ACTION_ROLLBACK: 3}.get(action, 0)

    def _reason(self, alpha, prev, action):
        if action == ACTION_ROLLBACK:
            return f"alpha={alpha:.4f} escalated from {prev}" if alpha < TAU_RB_HIGH else f"alpha={alpha:.4f} >= tau_rb_high={TAU_RB_HIGH}"
        if action == ACTION_REGENERATE:
            return f"alpha={alpha:.4f} in warn zone, escalated from {prev}"
        if action == ACTION_INJECT:
            return f"alpha={alpha:.4f} >= tau_warn_high={TAU_WARN_HIGH}"
        return f"alpha={alpha:.4f} below warn threshold, nominal"

    def reset(self):
        self._state = ACTION_CONTINUE
        self._last_alpha = 0.0
        self._anchor_history = []
        self._stable_streak = 0
        self._governor_active = False
