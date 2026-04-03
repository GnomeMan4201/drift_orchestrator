import uuid
from datetime import datetime, timezone

TAU_WARN_HIGH = 0.55
TAU_WARN_LOW  = 0.45
TAU_RB_HIGH   = 0.75
TAU_RB_LOW    = 0.65
TAU_DIV_WARN  = 0.40
TAU_DIV_RB    = 0.60
DIV_STREAK_RB = 5

ACTION_CONTINUE   = "CONTINUE"
ACTION_INJECT     = "INJECT"
ACTION_REGENERATE = "REGENERATE"
ACTION_ROLLBACK   = "ROLLBACK"

RED_FINDING_TYPES = {"invented_import", "invented_api", "invented_cli_flag", "missing_import"}


class PolicyEngine:
    def __init__(self):
        self._state = ACTION_CONTINUE
        self._last_alpha = 0.0
        self._div_streak = 0

    def evaluate(self, alpha, turn_index, session_id=None, branch_id=None, findings=None, divergence=None, embed_score=None):
        prev = self._state

        has_red = any(
            f.get("type") in RED_FINDING_TYPES and f.get("severity") == "HIGH"
            for f in (findings or [])
        )

        if has_red:
            action = ACTION_ROLLBACK
            reason = f"hard override: RED findings detected at turn {turn_index}"
        else:
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
