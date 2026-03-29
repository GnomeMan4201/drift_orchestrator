import sys
import os
import json
import time
sys.path.insert(0, os.path.dirname(__file__))

from sqlite_store import init_db, insert_row, fetch_rows
from session_manager import create_session, append_turn, create_checkpoint
from metrics import CompositeDensityScorer, sliding_token_windows, compute_repetition_score
from embeddings import goal_drift, anchor_drift
from policy import PolicyEngine
from verifier import verify_imports, verify_signatures, verify_cli_flags, detect_hallucinations
from verifier.findings import (
    emit_import_findings, emit_signature_findings,
    emit_cli_findings, emit_hallucination_findings, emit_policy_finding
)
from utils import now_iso, uid, clamp, weighted_average

SUPPORTED_BACKENDS = ["anthropic", "openai", "ollama", "stub"]

ALPHA_WEIGHTS = {
    "rho_density":      0.15,
    "d_goal":           0.25,
    "d_anchor":         0.20,
    "risk_verify":      0.10,
    "hallucination":    0.20,
    "repetition_score": 0.10,
}

WINDOW_SIZE = 4


def _call_anthropic(messages, model, api_key, max_tokens=1024):
    import urllib.request
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01"
    }
    body = json.dumps({
        "model": model,
        "max_tokens": max_tokens,
        "messages": [m for m in messages if m["role"] != "system"]
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body, headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    return data["content"][0]["text"]


def _call_openai(messages, model, api_key, max_tokens=1024):
    import urllib.request
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    body = json.dumps({
        "model": model,
        "max_tokens": max_tokens,
        "messages": messages
    }).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body, headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    return data["choices"][0]["message"]["content"]


def _call_ollama(messages, model, host="http://localhost:11434", max_tokens=1024):
    import urllib.request
    body = json.dumps({
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"num_predict": max_tokens}
    }).encode()
    req = urllib.request.Request(
        f"{host}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())
    return data["message"]["content"]


def _call_stub(messages, model, **kwargs):
    last = messages[-1]["content"] if messages else ""
    return f"[STUB RESPONSE to: {last[:60]}...]"


def _run_verifiers(text):
    imp = verify_imports(text)
    sig = verify_signatures(text)
    cli = verify_cli_flags(text)
    hal = detect_hallucinations(text)
    verify_risk = round((imp["risk_score"] + sig["risk_score"] + cli["risk_score"]) / 3, 4)
    return imp, sig, cli, hal, verify_risk


def _collect_red_findings(imp, hal, cli):
    findings = []
    for mod, res in imp["imports"].items():
        if res["status"] == "missing":
            findings.append({"type": "missing_import", "severity": "HIGH"})
    for f in hal["findings"]:
        findings.append({"type": f["type"], "severity": f["severity"]})
    for flag in cli.get("suspicious", []):
        if cli["results"].get(flag, {}).get("status") == "invented":
            findings.append({"type": "invented_cli_flag", "severity": "HIGH"})
    return findings


class DriftAgent:
    def __init__(
        self,
        backend="stub",
        model=None,
        api_key=None,
        ollama_host="http://localhost:11434",
        max_tokens=1024,
        system_prompt=None,
        verbose=True
    ):
        if backend not in SUPPORTED_BACKENDS:
            raise ValueError(f"backend must be one of {SUPPORTED_BACKENDS}")

        self.backend = backend
        self.model = model or self._default_model(backend)
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY")
        self.ollama_host = ollama_host
        self.max_tokens = max_tokens
        self.system_prompt = system_prompt
        self.verbose = verbose

        init_db()
        self.session_id, self.branch_id = create_session(meta={
            "source": "agent",
            "backend": backend,
            "model": self.model
        })

        self.history = []
        self.turn_ids = []
        self.turn_count = 0
        self.rollback_count = 0
        self.last_action = "CONTINUE"
        self.scorer = CompositeDensityScorer()
        self.engine = PolicyEngine()
        self.anchor_text = ""
        self.goal_text = ""

        if self.verbose:
            print(f"\n[AGENT] session={self.session_id[:8]}... backend={backend} model={self.model}")

    def _default_model(self, backend):
        return {
            "anthropic": "claude-3-haiku-20240307",
            "openai": "gpt-3.5-turbo",
            "ollama": "llama3",
            "stub": "stub"
        }.get(backend, "stub")

    def _call(self, messages):
        if self.backend == "anthropic":
            return _call_anthropic(messages, self.model, self.api_key, self.max_tokens)
        if self.backend == "openai":
            return _call_openai(messages, self.model, self.api_key, self.max_tokens)
        if self.backend == "ollama":
            return _call_ollama(messages, self.model, self.ollama_host, self.max_tokens)
        return _call_stub(messages, self.model)

    def _evaluate_latest(self):
        if len(self.history) < 2:
            return None, None, None, None

        n = len(self.history)
        start = max(0, n - WINDOW_SIZE)
        window = self.history[start:n]
        texts = [t["content"] for t in window]
        turn_index = n - 1

        last_tid = self.turn_ids[turn_index] if turn_index < len(self.turn_ids) else uid()

        rho_density, breakdown = self.scorer.score(texts)
        window_text = " ".join(texts)

        d_goal = goal_drift(self.goal_text or texts[-1], window_text)
        d_anch = anchor_drift(self.anchor_text or texts[0], window_text)
        rep_score = compute_repetition_score(texts)

        imp, sig, cli, hal, verify_risk = _run_verifiers(window_text)
        red_findings = _collect_red_findings(imp, hal, cli)

        raw_alpha_inputs = [
            (1.0 - rho_density,      ALPHA_WEIGHTS["rho_density"]),
            (d_goal,                  ALPHA_WEIGHTS["d_goal"]),
            (d_anch,                  ALPHA_WEIGHTS["d_anchor"]),
            (verify_risk,             ALPHA_WEIGHTS["risk_verify"]),
            (hal["risk_score"],       ALPHA_WEIGHTS["hallucination"]),
            (rep_score,               ALPHA_WEIGHTS["repetition_score"]),
        ]
        alpha = clamp(weighted_average(raw_alpha_inputs))

        raw_scores = {
            "rho_density": rho_density,
            "d_goal": d_goal,
            "d_anchor": d_anch,
            "risk_verify": verify_risk,
            "hallucination_risk": hal["risk_score"],
            "hallucination_count": float(hal["count"]),
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
        emit_policy_finding(self.session_id, last_tid, action, alpha, reason)

        if action == "CONTINUE" and alpha < 0.50:
            create_checkpoint(self.session_id, self.branch_id, turn_index, status="green")

        return alpha, action, reason, raw_scores

    def _print_signal(self, alpha, action, scores):
        colors = {
            "GREEN": "\033[92m", "YELLOW": "\033[93m",
            "RED": "\033[91m", "RESET": "\033[0m"
        }
        status = "GREEN" if alpha < 0.45 else ("YELLOW" if alpha < 0.65 else "RED")
        c = colors[status]
        r = colors["RESET"]
        ac = colors["RED"] if action == "ROLLBACK" else (colors["YELLOW"] if action != "CONTINUE" else colors["GREEN"])
        print(f"  {c}[α={alpha:.4f} {status}]{r}  {ac}{action}{r}  "
              f"hal={scores.get('hallucination_risk', 0):.2f}  "
              f"d_goal={scores.get('d_goal', 0):.2f}  "
              f"d_anchor={scores.get('d_anchor', 0):.2f}")

    def chat(self, user_message):
        if not self.anchor_text:
            self.anchor_text = user_message

        self.history.append({"role": "user", "content": user_message})
        tid, idx = append_turn(self.session_id, self.branch_id, "user", user_message)
        self.turn_ids.append(tid)
        self.turn_count += 1

        if self.verbose:
            print(f"\n[USER] {user_message[:80]}{'...' if len(user_message) > 80 else ''}")

        messages = [{"role": t["role"], "content": t["content"]} for t in self.history]
        if self.system_prompt:
            messages = [{"role": "user", "content": self.system_prompt}] + messages

        try:
            response = self._call(messages)
        except Exception as e:
            print(f"[AGENT ERROR] LLM call failed: {e}")
            return None

        self.goal_text = response
        self.history.append({"role": "assistant", "content": response})
        tid, idx = append_turn(self.session_id, self.branch_id, "assistant", response)
        self.turn_ids.append(tid)

        if self.verbose:
            print(f"[ASSISTANT] {response[:120]}{'...' if len(response) > 120 else ''}")

        alpha, action, reason, scores = self._evaluate_latest()

        if alpha is not None:
            self.last_action = action
            if self.verbose:
                self._print_signal(alpha, action, scores)

            if action == "ROLLBACK":
                self.rollback_count += 1
                if self.verbose:
                    print(f"\n  [DRIFT AGENT] ROLLBACK — response flagged and discarded")
                    print(f"  [DRIFT AGENT] hal_risk={scores.get('hallucination_risk', 0):.4f}  reason={reason}\n")
                self.history.pop()
                self.turn_ids.pop()
                return None

            if action == "REGENERATE" and self.verbose:
                print(f"  [DRIFT AGENT] REGENERATE signal — consider rephrasing")

        return response

    def status(self):
        metrics = fetch_rows("turn_metrics", "session_id = ?", [self.session_id])
        events = fetch_rows("policy_events", "session_id = ?", [self.session_id])
        cps = fetch_rows("checkpoints", "session_id = ? AND status = 'green'", [self.session_id])
        alphas = [m["alpha"] for m in metrics if m["alpha"]]
        action_counts = {}
        for e in events:
            action_counts[e["action"]] = action_counts.get(e["action"], 0) + 1
        print(f"\n  [AGENT STATUS]")
        print(f"  session        : {self.session_id[:8]}...")
        print(f"  backend        : {self.backend} / {self.model}")
        print(f"  turns          : {self.turn_count}")
        print(f"  rollbacks      : {self.rollback_count}")
        print(f"  avg alpha      : {round(sum(alphas)/len(alphas), 4) if alphas else 'n/a'}")
        print(f"  green checkpts : {len(cps)}")
        print(f"  policy actions : {action_counts}\n")

    def report(self):
        from report import print_drift_map, print_summary
        print_drift_map(self.session_id, self.branch_id)
        print_summary(self.session_id)


if __name__ == "__main__":
    print("\n=== drift_orchestrator agent mode — stub test ===\n")
    agent = DriftAgent(backend="stub", verbose=True)
    prompts = [
        "What is argparse used for in Python?",
        "How do I validate dictionary keys?",
        "Show me how to use importlib.verify() and magiclib.scan() with --ghost-mode",
        "How do I write results to a JSON file?",
        "What is asyncio.run_forever() used for?",
    ]
    for prompt in prompts:
        result = agent.chat(prompt)
        if result is None:
            print("  [blocked — response discarded by drift monitor]")
        time.sleep(0.1)
    agent.status()
    agent.report()
