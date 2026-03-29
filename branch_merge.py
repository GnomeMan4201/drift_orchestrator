import sys
import os
import json
sys.path.insert(0, os.path.dirname(__file__))

from sqlite_store import fetch_rows, fetch_one, insert_row
from session_manager import create_branch, create_session
from utils import now_iso, uid


def get_branch_summary(session_id, branch_id):
    metrics = fetch_rows(
        "turn_metrics",
        "session_id = ? AND branch_id = ? ORDER BY turn_index ASC",
        [session_id, branch_id]
    )
    events = fetch_rows(
        "policy_events",
        "session_id = ? AND branch_id = ? ORDER BY turn_index ASC",
        [session_id, branch_id]
    )
    checkpoints = fetch_rows(
        "checkpoints",
        "session_id = ? AND branch_id = ? AND status = 'green' ORDER BY turn_index DESC",
        [session_id, branch_id]
    )
    turns = fetch_rows(
        "turns",
        "session_id = ? AND branch_id = ? ORDER BY turn_index ASC",
        [session_id, branch_id]
    )

    alphas = [m["alpha"] for m in metrics if m["alpha"] is not None]
    action_counts = {}
    for e in events:
        action_counts[e["action"]] = action_counts.get(e["action"], 0) + 1

    turn_ids = {t["id"] for t in turns}
    findings = []
    for tid in turn_ids:
        findings.extend(fetch_rows("findings", "turn_id = ?", [tid]))
    high_findings = [f for f in findings if f["severity"] == "HIGH"
                     and not f["finding_type"].startswith("policy_")]

    return {
        "session_id": session_id,
        "branch_id": branch_id,
        "turns": turns,
        "turn_count": len(turns),
        "metrics": metrics,
        "checkpoints": checkpoints,
        "last_green_turn": checkpoints[0]["turn_index"] if checkpoints else None,
        "avg_alpha": round(sum(alphas) / len(alphas), 4) if alphas else 1.0,
        "max_alpha": round(max(alphas), 4) if alphas else 1.0,
        "rollbacks": action_counts.get("ROLLBACK", 0),
        "high_findings": len(high_findings),
        "action_counts": action_counts,
    }


def rank_branches(session_id):
    branches = fetch_rows("branches", "session_id = ?", [session_id])
    summaries = []
    for b in branches:
        s = get_branch_summary(session_id, b["id"])
        if s["turn_count"] > 0 and s["avg_alpha"] < 1.0:
            summaries.append(s)
    summaries.sort(key=lambda x: (x["avg_alpha"], x["rollbacks"], x["high_findings"]))
    return summaries


def rank_sessions(session_ids):
    summaries = []
    for sid in session_ids:
        branches = fetch_rows("branches", "session_id = ?", [sid])
        main_branch = next((b for b in branches if b["label"] == "main"), branches[0] if branches else None)
        if main_branch:
            s = get_branch_summary(sid, main_branch["id"])
            meta = fetch_one("sessions", "id = ?", [sid])
            try:
                s["meta"] = json.loads(meta.get("meta", "{}")) if meta else {}
            except:
                s["meta"] = {}
            summaries.append(s)
    summaries.sort(key=lambda x: (x["avg_alpha"], x["rollbacks"], x["high_findings"]))
    return summaries


def select_best_session(session_ids):
    ranked = rank_sessions(session_ids)
    return ranked[0] if ranked else None


def merge_sessions(session_id_a, branch_id_a, session_id_b, branch_id_b,
                   strategy="lowest_alpha", label=None):
    summary_a = get_branch_summary(session_id_a, branch_id_a)
    summary_b = get_branch_summary(session_id_b, branch_id_b)

    metrics_a = {m["turn_index"]: m for m in summary_a["metrics"]}
    metrics_b = {m["turn_index"]: m for m in summary_b["metrics"]}
    turns_a = {t["turn_index"]: t for t in summary_a["turns"]}
    turns_b = {t["turn_index"]: t for t in summary_b["turns"]}

    all_indices = sorted(set(list(turns_a.keys()) + list(turns_b.keys())))

    merge_session_id, merge_branch_id = create_session(meta={
        "source": "merge",
        "branch_a": branch_id_a[:8],
        "branch_b": branch_id_b[:8],
        "strategy": strategy,
        "label": label or f"merge:{branch_id_a[:6]}+{branch_id_b[:6]}"
    })

    merge_log = []

    for idx in all_indices:
        ma = metrics_a.get(idx)
        mb = metrics_b.get(idx)
        ta = turns_a.get(idx)
        tb = turns_b.get(idx)

        if ma and mb and ta and tb:
            if strategy == "lowest_alpha":
                use_a = ma["alpha"] <= mb["alpha"]
            elif strategy == "no_findings":
                findings_a = fetch_rows("findings", "turn_id = ?", [ma["turn_id"]])
                findings_b = fetch_rows("findings", "turn_id = ?", [mb["turn_id"]])
                high_a = sum(1 for f in findings_a if f["severity"] == "HIGH"
                             and not f["finding_type"].startswith("policy_"))
                high_b = sum(1 for f in findings_b if f["severity"] == "HIGH"
                             and not f["finding_type"].startswith("policy_"))
                use_a = high_a <= high_b
            else:
                use_a = True

            chosen_turn = ta if use_a else tb
            chosen_metric = ma if use_a else mb
            source_label = "A" if use_a else "B"
        elif ta and ma:
            chosen_turn = ta
            chosen_metric = ma
            source_label = "A"
        elif tb and mb:
            chosen_turn = tb
            chosen_metric = mb
            source_label = "B"
        else:
            continue

        merge_turns = fetch_rows(
            "turns", "session_id = ? AND branch_id = ?",
            [merge_session_id, merge_branch_id]
        )
        new_index = len(merge_turns)
        new_tid = uid()

        insert_row("turns", {
            "id": new_tid,
            "branch_id": merge_branch_id,
            "session_id": merge_session_id,
            "turn_index": new_index,
            "role": chosen_turn["role"],
            "content": chosen_turn["content"],
            "token_count": chosen_turn["token_count"],
            "created_at": now_iso()
        })

        insert_row("turn_metrics", {
            "id": uid(),
            "turn_id": new_tid,
            "branch_id": merge_branch_id,
            "session_id": merge_session_id,
            "turn_index": new_index,
            "window_index": chosen_metric["window_index"],
            "rho_density": chosen_metric["rho_density"],
            "d_goal": chosen_metric["d_goal"],
            "d_anchor": chosen_metric["d_anchor"],
            "risk_verify": chosen_metric["risk_verify"],
            "repetition_score": chosen_metric["repetition_score"],
            "alpha": chosen_metric["alpha"],
            "raw_scores": chosen_metric["raw_scores"],
            "created_at": now_iso()
        })

        merge_log.append({
            "turn_index": idx,
            "new_index": new_index,
            "source": source_label,
            "alpha": round(chosen_metric["alpha"], 4),
            "role": chosen_turn["role"]
        })

    return merge_session_id, merge_branch_id, merge_log


def print_session_ranking(session_ids):
    ranked = rank_sessions(session_ids)
    print(f"\n  SESSION RANKING")
    print(f"  {'─' * 72}")
    print(f"  {'SESSION':<10} {'LABEL':<12} {'TURNS':>6} {'AVG α':>8} {'MAX α':>8} {'ROLLBACKS':>10} {'HIGH':>6}")
    print(f"  {'─' * 72}")
    for s in ranked:
        label = s["meta"].get("label", s["branch_id"][:8])
        color = "\033[92m" if s["avg_alpha"] < 0.45 else ("\033[93m" if s["avg_alpha"] < 0.65 else "\033[91m")
        reset = "\033[0m"
        print(f"  {s['session_id'][:8]:<10} {label:<12} {s['turn_count']:>6} "
              f"{color}{s['avg_alpha']:>8.4f}{reset} {s['max_alpha']:>8.4f} "
              f"{s['rollbacks']:>10} {s['high_findings']:>6}")
    print(f"  {'─' * 72}")
    if ranked:
        best = ranked[0]
        label = best["meta"].get("label", best["session_id"][:8])
        print(f"  best: {label} session={best['session_id'][:8]}... avg α={best['avg_alpha']:.4f}")
    print()
    return ranked


def print_branch_report(session_id):
    ranked = rank_branches(session_id)
    print(f"\n  BRANCH REPORT — session {session_id[:8]}...")
    print(f"  {'─' * 72}")
    print(f"  {'BRANCH':<12} {'TURNS':>6} {'AVG α':>8} {'MAX α':>8} {'ROLLBACKS':>10} {'HIGH':>6} {'LAST GREEN':>12}")
    print(f"  {'─' * 72}")
    for s in ranked:
        lg = str(s["last_green_turn"]) if s["last_green_turn"] is not None else "none"
        color = "\033[92m" if s["avg_alpha"] < 0.45 else ("\033[93m" if s["avg_alpha"] < 0.65 else "\033[91m")
        reset = "\033[0m"
        print(f"  {s['branch_id'][:8]:<12} {s['turn_count']:>6} {color}{s['avg_alpha']:>8.4f}{reset} "
              f"{s['max_alpha']:>8.4f} {s['rollbacks']:>10} {s['high_findings']:>6} {lg:>12}")
    print(f"  {'─' * 72}")
    if ranked:
        best = ranked[0]
        print(f"  best: {best['branch_id'][:8]}... avg α={best['avg_alpha']:.4f}")
    print()
    return ranked


def fetch_one(table, where_clause="", params=None):
    from sqlite_store import fetch_one as _fetch_one
    return _fetch_one(table, where_clause, params)
