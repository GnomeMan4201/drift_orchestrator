import json
from sqlite_store import fetch_rows


STATUS_COLORS = {
    "GREEN": "\033[92m",
    "YELLOW": "\033[93m",
    "RED": "\033[91m",
    "RESET": "\033[0m",
}


def _alpha_to_status(alpha):
    if alpha < 0.45:
        return "GREEN"
    if alpha < 0.65:
        return "YELLOW"
    return "RED"


def _policy_label(action, level):
    return f"Level {level} {action}"


def print_drift_map(session_id, branch_id=None, turns=None):
    metrics = fetch_rows(
        "turn_metrics",
        "session_id = ?" + (" AND branch_id = ?" if branch_id else "") + " ORDER BY turn_index ASC, window_index ASC",
        [session_id, branch_id] if branch_id else [session_id]
    )

    events_raw = fetch_rows(
        "policy_events",
        "session_id = ?" + (" AND branch_id = ?" if branch_id else "") + " ORDER BY turn_index ASC",
        [session_id, branch_id] if branch_id else [session_id]
    )
    event_map = {e["turn_index"]: e for e in events_raw}

    turn_rows = fetch_rows(
        "turns",
        "session_id = ?" + (" AND branch_id = ?" if branch_id else "") + " ORDER BY turn_index ASC",
        [session_id, branch_id] if branch_id else [session_id]
    )
    turn_content_map = {t["turn_index"]: t["content"] for t in turn_rows}

    print("\n" + "=" * 72)
    print(f"  DRIFT MAP  |  session={session_id[:8]}...")
    print("=" * 72)

    seen_windows = set()
    for m in metrics:
        key = (m["turn_index"], m["window_index"])
        if key in seen_windows:
            continue
        seen_windows.add(key)

        alpha = m["alpha"] or 0.0
        rho = m["rho_density"] or 0.0
        status = _alpha_to_status(alpha)
        color = STATUS_COLORS[status]
        reset = STATUS_COLORS["RESET"]

        ev = event_map.get(m["turn_index"])
        policy_str = ""
        if ev:
            _level_map = {"CONTINUE": 0, "INJECT": 1, "REGENERATE": 2, "ROLLBACK": 3}
            policy_str = f"POLICY: {_policy_label(ev['action'], _level_map.get(ev['action'], 0))}"

        content = turn_content_map.get(m["turn_index"], "")
        claim = (content[:80] + "...") if len(content) > 80 else content
        claim = claim.replace("\n", " ")

        print(f"\n[TURN {m['turn_index']:>3}] Window {m['window_index']}:  rho={rho:.4f},  alpha={alpha:.4f}")
        print(f"  CLAIM:  {claim}")
        print(f"  STATUS: {color}{status}{reset}   {policy_str}")

        raw = m.get("raw_scores")
        if raw:
            try:
                scores = json.loads(raw)
                parts = [f"{k}={v:.4f}" for k, v in scores.items() if isinstance(v, float)]
                print(f"  SCORES: {', '.join(parts)}")
            except Exception:
                pass

    print("\n" + "=" * 72)
    print("  END OF DRIFT MAP")
    print("=" * 72 + "\n")


def print_summary(session_id):
    metrics = fetch_rows("turn_metrics", "session_id = ?", [session_id])
    events = fetch_rows("policy_events", "session_id = ?", [session_id])

    if not metrics:
        print("No metrics recorded.")
        return

    alphas = [m["alpha"] for m in metrics if m["alpha"] is not None]
    rhos = [m["rho_density"] for m in metrics if m["rho_density"] is not None]

    avg_alpha = sum(alphas) / len(alphas) if alphas else 0.0
    max_alpha = max(alphas) if alphas else 0.0
    avg_rho = sum(rhos) / len(rhos) if rhos else 0.0

    action_counts = {}
    for e in events:
        action_counts[e["action"]] = action_counts.get(e["action"], 0) + 1

    print("\n--- SESSION SUMMARY ---")
    print(f"  Turns evaluated : {len(set(m['turn_index'] for m in metrics))}")
    print(f"  Avg alpha (drift): {avg_alpha:.4f}")
    print(f"  Max alpha (drift): {max_alpha:.4f}")
    print(f"  Avg rho (density): {avg_rho:.4f}")
    print(f"  Policy actions   : {action_counts}")
    print("-----------------------\n")
