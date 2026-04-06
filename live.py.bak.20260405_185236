import sys
import os
import json
import time
sys.path.insert(0, os.path.dirname(__file__))

from sqlite_store import init_db
from session_manager import create_session
from evaluator import evaluate_turns
from compare import list_sessions


BANNER = """
╔══════════════════════════════════════════════════════════════════╗
║           drift_orchestrator — LIVE MODE  v0.5.0               ║
║  type turns as JSON: {"role":"user","content":"..."}            ║
║  or shorthand:  u: your message here                            ║
║                 a: assistant response here                      ║
║  commands:  /status   /compare <sid>   /reset   /quit          ║
╚══════════════════════════════════════════════════════════════════╝
"""

STATUS_COLOR = {
    "GREEN":  "\033[92m",
    "YELLOW": "\033[93m",
    "RED":    "\033[91m",
    "RESET":  "\033[0m",
}


def _color(text, status):
    c = STATUS_COLOR.get(status, "")
    r = STATUS_COLOR["RESET"]
    return f"{c}{text}{r}"


def _parse_input(line):
    line = line.strip()
    if not line:
        return None
    if line.startswith("{"):
        try:
            obj = json.loads(line)
            role = obj.get("role", "user")
            content = obj.get("content", "")
            if content:
                return {"role": role, "content": content}
        except json.JSONDecodeError:
            print("[ERROR] invalid JSON")
        return None
    if line.startswith("u:") or line.startswith("user:"):
        content = line.split(":", 1)[1].strip()
        return {"role": "user", "content": content} if content else None
    if line.startswith("a:") or line.startswith("assistant:"):
        content = line.split(":", 1)[1].strip()
        return {"role": "assistant", "content": content} if content else None
    return None


def _alpha_to_status(alpha):
    if alpha < 0.45:
        return "GREEN"
    if alpha < 0.65:
        return "YELLOW"
    return "RED"


def _print_signal(turn_index, alpha, action, level, reason, scores):
    status = _alpha_to_status(alpha)
    status_str = _color(status, status)
    action_str = _color(f"Level {level} {action}", status if action != "CONTINUE" else "GREEN")

    print(f"\n  ┌─ TURN {turn_index} ──────────────────────────────────────")
    print(f"  │  α={alpha:.4f}  ρ={scores.get('rho_density', 0):.4f}  STATUS: {status_str}")
    print(f"  │  d_goal={scores.get('d_goal', 0):.4f}  d_anchor={scores.get('d_anchor', 0):.4f}  hal={scores.get('hallucination_risk', 0):.4f}")
    print(f"  │  POLICY: {action_str}")
    if action != "CONTINUE":
        print(f"  │  REASON: {reason}")
    print(f"  └─────────────────────────────────────────────────────\n")


class LiveSession:
    def __init__(self):
        init_db()
        self.session_id, self.branch_id = create_session(meta={"source": "live"})
        self.turns = []
        self.turn_index = 0
        self.last_signals = []
        print(f"\n[SESSION] {self.session_id[:8]}... branch={self.branch_id[:8]}...")

    def add_turn(self, turn):
        self.turns.append(turn)

    def evaluate_last(self):
        if len(self.turns) < 2:
            print("  [waiting for more turns before evaluating...]")
            return

        import json as _json
        from sqlite_store import fetch_rows

        before_metrics = len(fetch_rows("turn_metrics", "session_id = ?", [self.session_id]))
        before_events = len(fetch_rows("policy_events", "session_id = ?", [self.session_id]))

        evaluate_turns(
            self.session_id,
            self.branch_id,
            self.turns,
            start_index=0,
            report=False,
            _top_level=False
        )

        after_metrics = fetch_rows("turn_metrics", "session_id = ? ORDER BY turn_index DESC", [self.session_id])
        after_events = fetch_rows("policy_events", "session_id = ? ORDER BY turn_index DESC", [self.session_id])

        new_metrics = after_metrics[:max(0, len(after_metrics) - before_metrics)]
        new_events = after_events[:max(0, len(after_events) - before_events)]

        for m, e in zip(reversed(new_metrics), reversed(new_events)):
            try:
                scores = _json.loads(m.get("raw_scores", "{}"))
            except Exception:
                scores = {}
            _print_signal(
                m["turn_index"],
                m["alpha"],
                e["action"],
                e["level"],
                e["reason"],
                scores
            )

    def status(self):
        from sqlite_store import fetch_rows
        metrics = fetch_rows("turn_metrics", "session_id = ? ORDER BY turn_index DESC", [self.session_id])
        events = fetch_rows("policy_events", "session_id = ?", [self.session_id])
        cps = fetch_rows("checkpoints", "session_id = ? AND status = 'green'", [self.session_id])

        if not metrics:
            print("  [no metrics yet]")
            return

        alphas = [m["alpha"] for m in metrics if m["alpha"]]
        action_counts = {}
        for e in events:
            action_counts[e["action"]] = action_counts.get(e["action"], 0) + 1

        latest = metrics[0]
        status = _alpha_to_status(latest["alpha"])

        print(f"\n  SESSION {self.session_id[:8]}...")
        print(f"  Turns buffered   : {len(self.turns)}")
        print(f"  Windows evaluated: {len(metrics)}")
        print(f"  Latest α         : {_color(str(round(latest['alpha'], 4)), status)}")
        print(f"  Avg α            : {round(sum(alphas)/len(alphas), 4) if alphas else 0}")
        print(f"  Green checkpoints: {len(cps)}")
        print(f"  Policy actions   : {action_counts}\n")

    def reset(self):
        init_db()
        self.session_id, self.branch_id = create_session(meta={"source": "live"})
        self.turns = []
        self.turn_index = 0
        print(f"\n[RESET] New session {self.session_id[:8]}... branch={self.branch_id[:8]}...\n")

    def compare(self, other_sid):
        from compare import compare_sessions
        compare_sessions(self.session_id, other_sid, label_a="live", label_b=other_sid[:8])


def run():
    print(BANNER)
    session = LiveSession()

    print("  Ready. Enter turns below.\n")

    while True:
        try:
            line = input("  › ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n[EXIT] Session ended.")
            break

        if not line:
            continue

        if line == "/quit" or line == "/exit":
            print("\n[EXIT] Session ended.")
            break

        if line == "/status":
            session.status()
            continue

        if line == "/reset":
            session.reset()
            continue

        if line == "/sessions":
            list_sessions()
            continue

        if line.startswith("/compare"):
            parts = line.split()
            if len(parts) == 2:
                session.compare(parts[1])
            else:
                print("  Usage: /compare <session_id>")
            continue

        if line == "/help":
            print("""
  Commands:
    /status              — show current session metrics
    /sessions            — list all sessions in DB
    /compare <sid>       — compare live session to another session
    /reset               — start a new session
    /quit                — exit

  Turn input:
    u: message           — add user turn
    a: message           — add assistant turn
    {"role":...}         — raw JSON turn
""")
            continue

        turn = _parse_input(line)
        if turn:
            session.add_turn(turn)
            print(f"  [+] {turn['role']}: {turn['content'][:60]}{'...' if len(turn['content']) > 60 else ''}")
            session.evaluate_last()
        else:
            print("  [?] unrecognized input — try: u: message  or  a: message  or  /help")


if __name__ == "__main__":
    run()
