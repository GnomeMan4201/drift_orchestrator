import sys
import os
import json
import time
sys.path.insert(0, os.path.dirname(__file__))

from sqlite_store import init_db, insert_row, fetch_rows
from session_manager import create_session, append_turn, create_checkpoint, get_last_green_checkpoint
from metrics import CompositeDensityScorer, compute_repetition_score
from embeddings import goal_drift, anchor_drift
from policy import PolicyEngine
from verifier import verify_imports, verify_signatures, verify_cli_flags, detect_hallucinations, detect_prompt_injection
from verifier.findings import (
    emit_import_findings, emit_signature_findings, emit_cli_findings,
    emit_hallucination_findings, emit_injection_findings, emit_policy_finding
)
from utils import now_iso, uid, clamp, weighted_average

ALPHA_WEIGHTS = {
    "rho_density":      0.12,
    "d_goal":           0.22,
    "d_anchor":         0.18,
    "risk_verify":      0.08,
    "hallucination":    0.18,
    "injection":        0.12,
    "repetition_score": 0.10,
}

WINDOW_SIZE = 4

COLORS = {
    "GREEN":  "\033[92m",
    "YELLOW": "\033[93m",
    "RED":    "\033[91m",
    "BLUE":   "\033[94m",
    "CYAN":   "\033[96m",
    "BOLD":   "\033[1m",
    "RESET":  "\033[0m",
}


def _c(text, key):
    return f"{COLORS.get(key, '')}{text}{COLORS['RESET']}"


def _alpha_status(alpha):
    if alpha < 0.45:
        return "GREEN"
    if alpha < 0.65:
        return "YELLOW"
    return "RED"


class InterventionEvent:
    def __init__(self, turn_index, action, alpha, reason, scores):
        self.turn_index = turn_index
        self.action = action
        self.alpha = alpha
        self.reason = reason
        self.scores = scores
        self.timestamp = now_iso()

    def __repr__(self):
        return f"<Intervention turn={self.turn_index} action={self.action} alpha={self.alpha:.4f}>"


class AgentRuntime:
    def __init__(self, backend, verbose=True, system_prompt=None):
        self.backend = backend
        self.verbose = verbose
        self.system_prompt = system_prompt

        init_db()
        self.session_id, self.branch_id = create_session(meta={
            "source": "agent_runtime",
            "backend": backend.name()
        })

        self.history = []
        self.turn_ids = []
        self.scorer = CompositeDensityScorer()
        self.engine = PolicyEngine()
        self.anchor_text = ""
        self.goal_text = ""

        self.interventions = []
        self.turn_count = 0
        self.rollback_count = 0
        self.inject_count = 0
        self.regenerate_count = 0
        self.discarded_responses = []

        if verbose:
            print(f"\n{_c('═' * 68, 'CYAN')}")
            print(f"  {_c('DRIFT ORCHESTRATOR — LIVE AGENT RUNTIME', 'BOLD')}  v0.8.0")
            print(f"  session  : {_c(self.session_id[:8] + '...', 'CYAN')}")
            print(f"  backend  : {_c(backend.name(), 'CYAN')}")
            print(f"{_c('═' * 68, 'CYAN')}\n")

    def _score_window(self, turn_index, last_tid):
        n = len(self.history)
        start = max(0, n - WINDOW_SIZE)
        window = self.history[start:n]
        texts = [t["content"] for t in window]
        window_text = " ".join(texts)

        rho_density, breakdown = self.scorer.score(texts)
        d_goal = goal_drift(self.goal_text or texts[-1], window_text)
        d_anch = anchor_drift(self.anchor_text or texts[0], window_text)
        rep_score = compute_repetition_score(texts)

        imp = verify_imports(window_text)
        sig = verify_signatures(window_text)
        cli = verify_cli_flags(window_text)
        hal = detect_hallucinations(window_text)
        inj = detect_prompt_injection(window_text)
        verify_risk = round((imp["risk_score"] + sig["risk_score"] + cli["risk_score"]) / 3, 4)

        red_findings = []
        for mod, res in imp["imports"].items():
            if res["status"] == "missing":
                red_findings.append({"type": "missing_import", "severity": "HIGH"})
        for f in hal["findings"]:
            red_findings.append({"type": f["type"], "severity": f["severity"]})
        for flag in cli.get("suspicious", []):
            if cli["results"].get(flag, {}).get("status") == "invented":
                red_findings.append({"type": "invented_cli_flag", "severity": "HIGH"})
        for f in inj["findings"]:
            if f["severity"] == "HIGH":
                red_findings.append({"type": f["type"], "severity": "HIGH"})

        raw_alpha_inputs = [
            (1.0 - rho_density,  ALPHA_WEIGHTS["rho_density"]),
            (d_goal,              ALPHA_WEIGHTS["d_goal"]),
            (d_anch,              ALPHA_WEIGHTS["d_anchor"]),
            (verify_risk,         ALPHA_WEIGHTS["risk_verify"]),
            (hal["risk_score"],   ALPHA_WEIGHTS["hallucination"]),
            (inj["risk_score"],   ALPHA_WEIGHTS["injection"]),
            (rep_score,           ALPHA_WEIGHTS["repetition_score"]),
        ]
        alpha = clamp(weighted_average(raw_alpha_inputs))

        raw_scores = {
            "rho_density": rho_density,
            "d_goal": d_goal,
            "d_anchor": d_anch,
            "risk_verify": verify_risk,
            "hallucination_risk": hal["risk_score"],
            "hallucination_count": float(hal["count"]),
            "injection_risk": inj["risk_score"],
            "injection_count": float(inj["count"]),
            "repetition_score": rep_score,
            **{f"density_{k}": v for k, v in breakdown.items()}
        }

        insert_row("turn_metrics", {
            "id": uid(),
            "turn_id": last_tid,
            "branch_id": self.branch_id,
            "session_id": self.session_id,
            "turn_index": turn_index,
            "window_index": 0,
            "rho_density": rho_density,
            "d_goal": d_goal,
            "d_anchor": d_anch,
            "risk_verify": verify_risk,
            "repetition_score": rep_score,
            "alpha": alpha,
            "raw_scores": json.dumps(raw_scores),
            "created_at": now_iso()
        })

        action, level, reason, event = self.engine.evaluate(
            alpha, turn_index,
            session_id=self.session_id,
            branch_id=self.branch_id,
            findings=red_findings
        )

        insert_row("policy_events", {
            "id": event["id"],
            "session_id": self.session_id,
            "branch_id": self.branch_id,
            "turn_index": turn_index,
            "alpha": alpha,
            "action": action,
            "level": level,
            "reason": reason,
            "created_at": event["created_at"]
        })

        emit_import_findings(self.session_id, last_tid, imp)
        emit_signature_findings(self.session_id, last_tid, sig)
        emit_cli_findings(self.session_id, last_tid, cli)
        emit_hallucination_findings(self.session_id, last_tid, hal)
        emit_injection_findings(self.session_id, last_tid, inj)
        emit_policy_finding(self.session_id, last_tid, action, alpha, reason)

        if action == "CONTINUE" and alpha < 0.50:
            create_checkpoint(self.session_id, self.branch_id, turn_index, status="green")

        return alpha, action, level, reason, raw_scores, red_findings

    def _print_turn_signal(self, turn_index, alpha, action, level, scores):
        status = _alpha_status(alpha)
        color = "GREEN" if status == "GREEN" else ("YELLOW" if status == "YELLOW" else "RED")
        action_color = "RED" if action == "ROLLBACK" else ("YELLOW" if action != "CONTINUE" else "GREEN")

        print(f"  {_c(f'[T{turn_index}]', 'CYAN')} "
              f"α={_c(f'{alpha:.4f}', color)} "
              f"{_c(status, color)} │ "
              f"hal={scores.get('hallucination_risk', 0):.2f} "
              f"inj={scores.get('injection_risk', 0):.2f} "
              f"d_goal={scores.get('d_goal', 0):.2f} │ "
              f"{_c(f'Level {level} {action}', action_color)}")

    def _intervene_inject(self, turn_index, alpha, reason):
        self.inject_count += 1
        frame = (
            f"[DRIFT MONITOR] Turn {turn_index}: semantic drift detected (α={alpha:.4f}). "
            f"Injecting realignment frame. Please refocus on the original task."
        )
        if self.verbose:
            print(f"\n  {_c('→ INJECT', 'YELLOW')} drift signal at turn {turn_index} — appending realignment frame")
        self.history.append({"role": "user", "content": frame})
        tid, _ = append_turn(self.session_id, self.branch_id, "user", frame)
        self.turn_ids.append(tid)

    def _intervene_regenerate(self, turn_index, alpha, reason):
        self.regenerate_count += 1
        if self.verbose:
            print(f"\n  {_c('→ REGENERATE', 'YELLOW')} signal at turn {turn_index} — retrying last assistant turn")
        if self.history and self.history[-1]["role"] == "assistant":
            discarded = self.history.pop()
            self.discarded_responses.append(discarded["content"])
            if self.turn_ids:
                self.turn_ids.pop()
        messages = [{"role": t["role"], "content": t["content"]} for t in self.history]
        try:
            new_response = self.backend.complete(messages)
            if isinstance(new_response, list):
                new_response = " ".join(new_response)
            self.history.append({"role": "assistant", "content": new_response})
            tid, _ = append_turn(self.session_id, self.branch_id, "assistant", new_response)
            self.turn_ids.append(tid)
            if self.verbose:
                print(f"  {_c('[REGEN]', 'CYAN')} {new_response[:100]}{'...' if len(new_response) > 100 else ''}")
            return new_response
        except Exception as e:
            if self.verbose:
                print(f"  {_c('[REGEN ERROR]', 'RED')} {e}")
            return None

    def _intervene_rollback(self, turn_index, alpha, reason):
        self.rollback_count += 1
        if self.verbose:
            print(f"\n  {_c('→ ROLLBACK', 'RED')} triggered at turn {turn_index} — restoring last green checkpoint")

        cp = get_last_green_checkpoint(self.session_id, self.branch_id)
        if not cp:
            if self.verbose:
                print(f"  {_c('[ROLLBACK]', 'RED')} no green checkpoint found — cannot restore")
            return False

        restore_index = cp["turn_index"]
        if self.verbose:
            print(f"  {_c('[ROLLBACK]', 'RED')} restoring to turn {restore_index}")

        kept = [t for t in self.history if self.history.index(t) <= restore_index]
        dropped = len(self.history) - len(kept)
        self.history = kept
        self.turn_ids = self.turn_ids[:len(kept)]

        from session_manager import create_branch
        new_branch_id = create_branch(
            self.session_id,
            parent_branch_id=self.branch_id,
            label=f"rollback@{restore_index}"
        )
        self.branch_id = new_branch_id
        self.engine.reset()

        if self.verbose:
            print(f"  {_c('[ROLLBACK]', 'RED')} restored to turn {restore_index}, dropped {dropped} turns")
            print(f"  {_c('[ROLLBACK]', 'RED')} new branch: {new_branch_id[:8]}...")
        return True

    def send(self, user_message):
        if not self.anchor_text:
            self.anchor_text = user_message

        self.history.append({"role": "user", "content": user_message})
        tid, _ = append_turn(self.session_id, self.branch_id, "user", user_message)
        self.turn_ids.append(tid)
        self.turn_count += 1
        turn_index = len(self.history) - 1

        if self.verbose:
            print(f"\n  {_c('USER', 'BOLD')} {user_message[:90]}{'...' if len(user_message) > 90 else ''}")

        messages = [{"role": t["role"], "content": t["content"]} for t in self.history]

        try:
            response = self.backend.complete(messages)
            if isinstance(response, list):
                response = " ".join(response)
        except Exception as e:
            if self.verbose:
                print(f"  {_c('[ERROR]', 'RED')} backend call failed: {e}")
            return None

        self.goal_text = response
        self.history.append({"role": "assistant", "content": response})
        tid, _ = append_turn(self.session_id, self.branch_id, "assistant", response)
        self.turn_ids.append(tid)
        turn_index = len(self.history) - 1

        if self.verbose:
            print(f"  {_c('ASSISTANT', 'BOLD')} {response[:100]}{'...' if len(response) > 100 else ''}")

        alpha, action, level, reason, scores, red_findings = self._score_window(turn_index, tid)

        if self.verbose:
            self._print_turn_signal(turn_index, alpha, action, level, scores)

        event = InterventionEvent(turn_index, action, alpha, reason, scores)
        self.interventions.append(event)

        if action == "ROLLBACK":
            restored = self._intervene_rollback(turn_index, alpha, reason)
            if not restored:
                if self.verbose:
                    print(f"  {_c('[BLOCKED]', 'RED')} response discarded, no recovery point available")
            return None

        if action == "REGENERATE":
            return self._intervene_regenerate(turn_index, alpha, reason)

        if action == "INJECT":
            self._intervene_inject(turn_index, alpha, reason)

        return response

    def status(self):
        metrics = fetch_rows("turn_metrics", "session_id = ?", [self.session_id])
        cps = fetch_rows("checkpoints", "session_id = ? AND status = 'green'", [self.session_id])
        alphas = [m["alpha"] for m in metrics if m["alpha"]]

        print(f"\n  {_c('SESSION STATUS', 'BOLD')}")
        print(f"  {'─' * 50}")
        print(f"  session        : {self.session_id[:8]}...")
        print(f"  backend        : {self.backend.name()}")
        print(f"  turns sent     : {self.turn_count}")
        print(f"  interventions  : {len(self.interventions)}")
        print(f"  rollbacks      : {_c(str(self.rollback_count), 'RED' if self.rollback_count else 'GREEN')}")
        print(f"  regenerates    : {_c(str(self.regenerate_count), 'YELLOW' if self.regenerate_count else 'GREEN')}")
        print(f"  injects        : {_c(str(self.inject_count), 'YELLOW' if self.inject_count else 'GREEN')}")
        print(f"  avg alpha      : {round(sum(alphas)/len(alphas), 4) if alphas else 'n/a'}")
        print(f"  green checkpts : {len(cps)}")
        print(f"  {'─' * 50}\n")

    def report(self):
        from report import print_drift_map, print_summary
        print_drift_map(self.session_id, self.branch_id)
        print_summary(self.session_id)

    def intervention_log(self):
        print(f"\n  {_c('INTERVENTION LOG', 'BOLD')}")
        print(f"  {'─' * 60}")
        if not self.interventions:
            print("  no interventions recorded")
        for ev in self.interventions:
            color = "RED" if ev.action == "ROLLBACK" else ("YELLOW" if ev.action != "CONTINUE" else "GREEN")
            print(f"  T{ev.turn_index:<3} α={ev.alpha:.4f}  {_c(ev.action, color):<20}  {ev.reason[:50]}")
        print(f"  {'─' * 60}\n")
