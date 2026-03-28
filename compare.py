import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from sqlite_store import fetch_rows
from utils import now_iso


def _get_session_metrics(session_id):
    return fetch_rows(
        "turn_metrics",
        "session_id = ? ORDER BY turn_index ASC",
        [session_id]
    )


def _get_session_events(session_id):
    return fetch_rows(
        "policy_events",
        "session_id = ? ORDER BY turn_index ASC",
        [session_id]
    )


def _get_session_findings(session_id):
    return fetch_rows(
        "findings",
        "session_id = ? ORDER BY created_at ASC",
        [session_id]
    )


def _get_session_meta(session_id):
    from sqlite_store import fetch_one
    return fetch_one("sessions", "id = ?", [session_id])


def _summarize(session_id):
    metrics = _get_session_metrics(session_id)
    events = _get_session_events(session_id)
    findings = _get_session_findings(session_id)
    meta = _get_session_meta(session_id)

    if not metrics:
        return None

    alphas = [m["alpha"] for m in metrics if m["alpha"] is not None]
    rhos = [m["rho_density"] for m in metrics if m["rho_density"] is not None]
    d_goals = [m["d_goal"] for m in metrics if m["d_goal"] is not None]
    d_anchors = [m["d_anchor"] for m in metrics if m["d_anchor"] is not None]

    action_counts = {}
    for e in events:
        action_counts[e["action"]] = action_counts.get(e["action"], 0) + 1

    finding_counts = {}
    for f in findings:
        key = f"{f['severity']}:{f['finding_type']}"
        finding_counts[key] = finding_counts.get(key, 0) + 1

    high_findings = [f for f in findings if f["severity"] == "HIGH" and not f["finding_type"].startswith("policy_")]

    return {
        "session_id": session_id,
        "source": meta.get("meta", "{}") if meta else "{}",
        "turns": len(set(m["turn_index"] for m in metrics)),
        "windows": len(metrics),
        "avg_alpha": round(sum(alphas) / len(alphas), 4) if alphas else 0.0,
        "max_alpha": round(max(alphas), 4) if alphas else 0.0,
        "min_alpha": round(min(alphas), 4) if alphas else 0.0,
        "avg_rho": round(sum(rhos) / len(rhos), 4) if rhos else 0.0,
        "avg_d_goal": round(sum(d_goals) / len(d_goals), 4) if d_goals else 0.0,
        "avg_d_anchor": round(sum(d_anchors) / len(d_anchors), 4) if d_anchors else 0.0,
        "action_counts": action_counts,
        "finding_counts": finding_counts,
        "high_findings": len(high_findings),
        "rollbacks": action_counts.get("ROLLBACK", 0),
        "injects": action_counts.get("INJECT", 0),
        "regenerates": action_counts.get("REGENERATE", 0),
    }


def _delta(a, b, key):
    va = a.get(key, 0.0)
    vb = b.get(key, 0.0)
    diff = round(vb - va, 4)
    direction = "↑" if diff > 0 else ("↓" if diff < 0 else "=")
    return diff, direction


def compare_sessions(session_id_a, session_id_b, label_a="A", label_b="B"):
    sa = _summarize(session_id_a)
    sb = _summarize(session_id_b)

    if not sa:
        print(f"[COMPARE] No data for session {session_id_a[:8]}")
        return
    if not sb:
        print(f"[COMPARE] No data for session {session_id_b[:8]}")
        return

    print("\n" + "=" * 72)
    print(f"  DRIFT DELTA  |  {label_a}: {session_id_a[:8]}...  vs  {label_b}: {session_id_b[:8]}...")
    print("=" * 72)

    metrics = [
        ("avg_alpha",    "Avg α (drift)   "),
        ("max_alpha",    "Max α (drift)   "),
        ("avg_rho",      "Avg ρ (density) "),
        ("avg_d_goal",   "Avg d_goal      "),
        ("avg_d_anchor", "Avg d_anchor    "),
    ]

    print(f"\n  {'METRIC':<22} {label_a:>10} {label_b:>10} {'DELTA':>10} {'DIR':>4}")
    print("  " + "-" * 58)

    for key, label in metrics:
        va = sa.get(key, 0.0)
        vb = sb.get(key, 0.0)
        diff, direction = _delta(sa, sb, key)
        print(f"  {label:<22} {va:>10.4f} {vb:>10.4f} {diff:>+10.4f} {direction:>4}")

    print(f"\n  {'POLICY ACTIONS':<22} {label_a:>10} {label_b:>10}")
    print("  " + "-" * 44)
    all_actions = set(sa["action_counts"]) | set(sb["action_counts"])
    for action in sorted(all_actions):
        va = sa["action_counts"].get(action, 0)
        vb = sb["action_counts"].get(action, 0)
        diff = vb - va
        direction = "↑" if diff > 0 else ("↓" if diff < 0 else "=")
        print(f"  {action:<22} {va:>10} {vb:>10}  {direction} {abs(diff)}")

    print(f"\n  {'FINDINGS':<22} {label_a:>10} {label_b:>10}")
    print("  " + "-" * 44)
    print(f"  {'HIGH findings':<22} {sa['high_findings']:>10} {sb['high_findings']:>10}  {'↑' if sb['high_findings'] > sa['high_findings'] else '↓' if sb['high_findings'] < sa['high_findings'] else '='} {abs(sb['high_findings'] - sa['high_findings'])}")

    print(f"\n  {'VERDICT'}")
    print("  " + "-" * 58)

    alpha_delta = sb["avg_alpha"] - sa["avg_alpha"]
    rb_delta = sb["rollbacks"] - sa["rollbacks"]
    hf_delta = sb["high_findings"] - sa["high_findings"]

    if alpha_delta > 0.05 or rb_delta > 0 or hf_delta > 0:
        worse = []
        if alpha_delta > 0.05:
            worse.append(f"higher avg drift (+{alpha_delta:.4f})")
        if rb_delta > 0:
            worse.append(f"more rollbacks (+{rb_delta})")
        if hf_delta > 0:
            worse.append(f"more HIGH findings (+{hf_delta})")
        print(f"  {label_b} is WORSE than {label_a}: {', '.join(worse)}")
    elif alpha_delta < -0.05 or rb_delta < 0 or hf_delta < 0:
        better = []
        if alpha_delta < -0.05:
            better.append(f"lower avg drift ({alpha_delta:.4f})")
        if rb_delta < 0:
            better.append(f"fewer rollbacks ({rb_delta})")
        if hf_delta < 0:
            better.append(f"fewer HIGH findings ({hf_delta})")
        print(f"  {label_b} is BETTER than {label_a}: {', '.join(better)}")
    else:
        print(f"  {label_a} and {label_b} are broadly equivalent within tolerance")

    print("=" * 72 + "\n")
    return sa, sb


def list_sessions():
    from sqlite_store import fetch_rows
    import json
    sessions = fetch_rows("sessions", "", [])
    print(f"\n{'SESSION ID':<38} {'CREATED':<26} SOURCE")
    print("-" * 80)
    for s in sessions:
        try:
            meta = json.loads(s.get("meta", "{}"))
            source = meta.get("source", "unknown")
        except Exception:
            source = "unknown"
        print(f"{s['id']:<38} {s['created_at'][:19]:<26} {source}")
    print()
    return sessions


if __name__ == "__main__":
    if len(sys.argv) == 1:
        list_sessions()
    elif len(sys.argv) == 3:
        compare_sessions(sys.argv[1], sys.argv[2])
    elif len(sys.argv) == 5:
        compare_sessions(sys.argv[1], sys.argv[2], label_a=sys.argv[3], label_b=sys.argv[4])
    else:
        print("Usage:")
        print("  python3 compare.py                          # list sessions")
        print("  python3 compare.py <session_a> <session_b>  # compare two sessions")
        print("  python3 compare.py <sid_a> <sid_b> A B      # compare with labels")
