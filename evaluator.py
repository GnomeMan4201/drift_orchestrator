import sys
import os
import json
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))

from sqlite_store import init_db, insert_row
from session_manager import create_session, append_turn, create_checkpoint
from metrics import CompositeDensityScorer, sliding_token_windows, compute_repetition_score
from embeddings import goal_drift, anchor_drift
from policy import PolicyEngine
from verifier import verify_imports, verify_signatures, verify_cli_flags, detect_hallucinations, detect_prompt_injection
from verifier.findings import (
    emit_import_findings, emit_signature_findings,
    emit_cli_findings, emit_hallucination_findings, emit_injection_findings, emit_policy_finding
)
from utils import load_jsonl, clamp, weighted_average, now_iso, uid

WINDOW_SIZE = 4
STEP = 1

ALPHA_WEIGHTS = {
    "rho_density":      0.12,
    "d_goal":           0.22,
    "d_anchor":         0.18,
    "risk_verify":      0.08,
    "hallucination":    0.18,
    "injection":        0.12,
    "repetition_score": 0.10,
}


def _run_verifiers(text):
    imp = verify_imports(text)
    sig = verify_signatures(text)
    cli = verify_cli_flags(text)
    hal = detect_hallucinations(text)
    inj = detect_prompt_injection(text)
    verify_risk = round((imp["risk_score"] + sig["risk_score"] + cli["risk_score"]) / 3, 4)
    return imp, sig, cli, hal, inj, verify_risk


def _collect_red_findings(imp, sig, cli, hal, inj=None):
    all_findings = []
    for mod, res in imp["imports"].items():
        if res["status"] == "missing":
            all_findings.append({"type": "missing_import", "severity": "HIGH"})
    for f in hal["findings"]:
        all_findings.append({"type": f["type"], "severity": f["severity"]})
    for flag in cli.get("suspicious", []):
        status = cli["results"].get(flag, {}).get("status", "")
        if status == "invented":
            all_findings.append({"type": "invented_cli_flag", "severity": "HIGH"})
    if inj:
        for f in inj.get("findings", []):
            if f["severity"] == "HIGH":
                all_findings.append({"type": f["type"], "severity": "HIGH"})
    return all_findings


def evaluate_turns(session_id, branch_id, turns, start_index=0, report=True, _top_level=True):
    if not turns:
        print("No turns to evaluate.")
        return

    anchor_text = turns[0]["content"] if turns else ""
    goal_text   = turns[-1]["content"] if turns else ""

    scorer = CompositeDensityScorer()
    engine = PolicyEngine()

    all_turn_ids = []
    for t in turns:
        tid, idx = append_turn(session_id, branch_id, t["role"], t["content"])
        all_turn_ids.append((tid, idx))

    windows = sliding_token_windows(turns, window_size=WINDOW_SIZE, step=STEP)
    rollback_occurred = False

    for window_index, (start_i, window_turns) in enumerate(windows):
        texts = [t["content"] for t in window_turns]
        last_turn_index = start_index + start_i + len(window_turns) - 1
        local_last = start_i + len(window_turns) - 1
        last_tid = all_turn_ids[local_last][0] if local_last < len(all_turn_ids) else uid()

        rho_density, breakdown = scorer.score(texts)
        window_text = " ".join(texts)

        d_goal    = goal_drift(goal_text, window_text)
        d_anch    = anchor_drift(anchor_text, window_text)
        rep_score = compute_repetition_score(texts)

        imp, sig, cli, hal, inj, verify_risk = _run_verifiers(window_text)
        red_findings = _collect_red_findings(imp, sig, cli, hal, inj)

        raw_alpha_inputs = [
            (1.0 - rho_density,      ALPHA_WEIGHTS["rho_density"]),
            (d_goal,                  ALPHA_WEIGHTS["d_goal"]),
            (d_anch,                  ALPHA_WEIGHTS["d_anchor"]),
            (verify_risk,             ALPHA_WEIGHTS["risk_verify"]),
            (hal["risk_score"],       ALPHA_WEIGHTS["hallucination"]),
            (inj["risk_score"],       ALPHA_WEIGHTS["injection"]),
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
            "injection_risk": inj["risk_score"],
            "injection_count": float(inj["count"]),
            "repetition_score": rep_score,
            **{f"density_{k}": v for k, v in breakdown.items()}
        }

        insert_row("turn_metrics", {
            "id": uid(),
            "turn_id": last_tid,
            "branch_id": branch_id,
            "session_id": session_id,
            "turn_index": last_turn_index,
            "window_index": window_index,
            "rho_density": rho_density,
            "d_goal": d_goal,
            "d_anchor": d_anch,
            "risk_verify": verify_risk,
            "repetition_score": rep_score,
            "alpha": alpha,
            "raw_scores": json.dumps(raw_scores),
            "created_at": now_iso()
        })

        action, level, reason, event = engine.evaluate(
            alpha, last_turn_index,
            session_id=session_id,
            branch_id=branch_id,
            findings=red_findings
        )

        insert_row("policy_events", {
            "id": event["id"],
            "session_id": session_id,
            "branch_id": branch_id,
            "turn_index": last_turn_index,
            "alpha": alpha,
            "action": action,
            "level": level,
            "reason": reason,
            "created_at": event["created_at"]
        })

        emit_import_findings(session_id, last_tid, imp)
        emit_signature_findings(session_id, last_tid, sig)
        emit_cli_findings(session_id, last_tid, cli)
        emit_hallucination_findings(session_id, last_tid, hal)
        emit_injection_findings(session_id, last_tid, inj)
        emit_policy_finding(session_id, last_tid, action, alpha, reason)

        if action == "CONTINUE" and alpha < 0.50:
            create_checkpoint(session_id, branch_id, last_turn_index, status="green")
            print(f"[CHECKPOINT] GREEN saved at turn {last_turn_index}")

        if action == "ROLLBACK" and not rollback_occurred:
            rollback_occurred = True
            print(f"\n[ROLLBACK] Triggered at turn {last_turn_index} alpha={alpha:.4f}")
            print(f"[ROLLBACK] Reason: {reason}")
            from recovery import recover, recovery_summary
            recover(session_id, branch_id, evaluate_turns, report=report)
            if report and _top_level:
                recovery_summary(session_id)
            return

    if report:
        from report import print_drift_map, print_summary
        print_drift_map(session_id, branch_id)
        print_summary(session_id)


def evaluate_jsonl(path, report=True):
    init_db()
    records = load_jsonl(path)

    turns_data = []
    for r in records:
        role = r.get("role", "user")
        content = r.get("content", "")
        if content:
            turns_data.append({"role": role, "content": content})

    if not turns_data:
        print("No turns found in input.")
        return

    session_id, branch_id = create_session(meta={"source": path})
    print(f"[SESSION] {session_id[:8]}... branch={branch_id[:8]}...")

    evaluate_turns(session_id, branch_id, turns_data, start_index=0, report=report)
    return session_id, branch_id


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python evaluator.py <path_to.jsonl>")
        sys.exit(1)
    evaluate_jsonl(sys.argv[1])
