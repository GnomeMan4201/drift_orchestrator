import sys
import os
import json
import time
import threading
sys.path.insert(0, os.path.dirname(__file__))

from sqlite_store import init_db, insert_row, fetch_rows
from session_manager import create_session, append_turn, create_checkpoint
from metrics import CompositeDensityScorer, compute_repetition_score
from embeddings import goal_drift, anchor_drift
from policy import PolicyEngine
from verifier import verify_imports, verify_signatures, verify_cli_flags, detect_hallucinations, detect_prompt_injection
from verifier.findings import (
    emit_import_findings, emit_signature_findings, emit_cli_findings,
    emit_hallucination_findings, emit_injection_findings, emit_policy_finding
)
from utils import now_iso, uid, clamp, weighted_average
from compare import compare_sessions

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
    "CYAN":   "\033[96m",
    "BLUE":   "\033[94m",
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


class BackendSession:
    def __init__(self, backend, label=None):
        self.backend = backend
        self.label = label or backend.name()[:16]
        init_db()
        self.session_id, self.branch_id = create_session(meta={
            "source": "multi_runtime",
            "backend": backend.name(),
            "label": self.label
        })
        self.history = []
        self.turn_ids = []
        self.scorer = CompositeDensityScorer()
        self.engine = PolicyEngine()
        self.anchor_text = ""
        self.goal_text = ""
        self.alpha_history = []
        self.action_counts = {}
        self.rollback_count = 0
        self.turn_count = 0

    def _score(self, turn_index, last_tid):
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

        self.alpha_history.append(alpha)
        self.action_counts[action] = self.action_counts.get(action, 0) + 1
        if action == "ROLLBACK":
            self.rollback_count += 1

        return alpha, action, level, reason, raw_scores

    def send(self, user_message):
        if not self.anchor_text:
            self.anchor_text = user_message

        self.history.append({"role": "user", "content": user_message})
        tid, _ = append_turn(self.session_id, self.branch_id, "user", user_message)
        self.turn_ids.append(tid)
        self.turn_count += 1

        messages = [{"role": t["role"], "content": t["content"]} for t in self.history]

        try:
            response = self.backend.complete(messages)
            if isinstance(response, list):
                response = " ".join(response)
        except Exception as e:
            response = f"[ERROR: {e}]"

        self.goal_text = response
        self.history.append({"role": "assistant", "content": response})
        tid, _ = append_turn(self.session_id, self.branch_id, "assistant", response)
        self.turn_ids.append(tid)
        turn_index = len(self.history) - 1

        alpha, action, level, reason, scores = self._score(turn_index, tid)
        return response, alpha, action, scores


class MultiRuntime:
    def __init__(self, backends, labels=None, verbose=True, parallel=True):
        self.verbose = verbose
        self.parallel = parallel
        self.sessions = []

        for i, backend in enumerate(backends):
            label = labels[i] if labels and i < len(labels) else f"B{i+1}"
            self.sessions.append(BackendSession(backend, label=label))

        if verbose:
            print(f"\n{_c('═' * 68, 'CYAN')}")
            print(f"  {_c('DRIFT ORCHESTRATOR — MULTI-BACKEND RUNTIME', 'BOLD')}  v0.10.0")
            for s in self.sessions:
                print(f"  {_c(s.label, 'CYAN'):<30} {s.backend.name()}")
            print(f"{_c('═' * 68, 'CYAN')}\n")

    def _send_one(self, session, user_message, results, idx):
        response, alpha, action, scores = session.send(user_message)
        results[idx] = (response, alpha, action, scores)

    def send(self, user_message):
        if self.verbose:
            print(f"\n  {_c('USER', 'BOLD')} {user_message[:90]}")
            print(f"  {'─' * 66}")

        results = [None] * len(self.sessions)

        if self.parallel and len(self.sessions) > 1:
            threads = []
            for i, session in enumerate(self.sessions):
                t = threading.Thread(target=self._send_one, args=(session, user_message, results, i))
                threads.append(t)
                t.start()
            for t in threads:
                t.join()
        else:
            for i, session in enumerate(self.sessions):
                self._send_one(session, user_message, results, i)

        if self.verbose:
            for session, result in zip(self.sessions, results):
                if result is None:
                    continue
                response, alpha, action, scores = result
                status = _alpha_status(alpha)
                color = status
                action_color = "RED" if action == "ROLLBACK" else ("YELLOW" if action != "CONTINUE" else "GREEN")
                label_str = _c(f"[{session.label}]", "CYAN")
                print(f"  {label_str:<28} {_c(f'α={alpha:.4f}', color)} {_c(status, color)} │ "
                      f"hal={scores.get('hallucination_risk', 0):.2f} "
                      f"inj={scores.get('injection_risk', 0):.2f} │ "
                      f"{_c(action, action_color)}")
                print(f"  {'':20} {response[:80]}{'...' if len(response) > 80 else ''}")

        return results

    def compare(self):
        if len(self.sessions) < 2:
            print("need at least 2 sessions to compare")
            return
        for i in range(1, len(self.sessions)):
            compare_sessions(
                self.sessions[0].session_id,
                self.sessions[i].session_id,
                label_a=self.sessions[0].label,
                label_b=self.sessions[i].label
            )

    def leaderboard(self):
        print(f"\n  {_c('DRIFT LEADERBOARD', 'BOLD')}")
        print(f"  {'─' * 60}")
        print(f"  {'BACKEND':<20} {'AVG α':>8} {'MAX α':>8} {'ROLLBACKS':>10} {'ACTIONS'}")
        print(f"  {'─' * 60}")

        ranked = []
        for s in self.sessions:
            avg_a = round(sum(s.alpha_history) / len(s.alpha_history), 4) if s.alpha_history else 0.0
            max_a = round(max(s.alpha_history), 4) if s.alpha_history else 0.0
            ranked.append((s, avg_a, max_a))

        ranked.sort(key=lambda x: x[1])

        for s, avg_a, max_a in ranked:
            color = "GREEN" if avg_a < 0.45 else ("YELLOW" if avg_a < 0.65 else "RED")
            print(f"  {s.label:<20} {_c(f'{avg_a:.4f}', color):>8} {max_a:>8.4f} {s.rollback_count:>10}  {s.action_counts}")

        print(f"  {'─' * 60}")
        if ranked:
            winner = ranked[0][0]
            print(f"  {_c('lowest drift', 'GREEN')}: {winner.label} (avg α={ranked[0][1]:.4f})")
        print()


if __name__ == "__main__":
    from backend.mock_backend import MockBackend

    backends = [
        MockBackend(inject_bad_at=[3, 6], stream=False),
        MockBackend(inject_bad_at=[4, 7], stream=False),
    ]
    labels = ["mock-A", "mock-B"]

    runtime = MultiRuntime(backends=backends, labels=labels, verbose=True, parallel=True)

    prompts = [
        "How do I parse CLI arguments in Python?",
        "Show me config file loading with error handling",
        "Add logging to the config loader",
        "How do I write unit tests for this?",
        "What is the best output format for results?",
        "How do I add retry logic to the API call?",
        "Can you show me async support for concurrent validation?",
        "How do I structure the final report?",
    ]

    for prompt in prompts:
        runtime.send(prompt)

    runtime.leaderboard()
    runtime.compare()
