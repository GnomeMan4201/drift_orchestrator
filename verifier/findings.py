import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from sqlite_store import insert_row
from utils import uid, now_iso


def emit_finding(session_id, turn_id, finding_type, severity, detail):
    insert_row("findings", {
        "id": uid(),
        "turn_id": turn_id,
        "session_id": session_id,
        "finding_type": finding_type,
        "severity": severity,
        "detail": detail,
        "created_at": now_iso()
    })


def emit_import_findings(session_id, turn_id, verify_result):
    for mod, res in verify_result["imports"].items():
        if res["status"] not in ("ok", "error"):
            emit_finding(
                session_id, turn_id,
                finding_type="missing_import",
                severity="HIGH",
                detail=f"module='{mod}' status={res['status']}"
            )


def emit_signature_findings(session_id, turn_id, verify_result):
    for issue in verify_result.get("issues", []):
        emit_finding(
            session_id, turn_id,
            finding_type=issue["type"],
            severity="MEDIUM",
            detail=issue["detail"]
        )


def emit_cli_findings(session_id, turn_id, verify_result):
    for flag in verify_result.get("suspicious", []):
        status = verify_result["results"].get(flag, {}).get("status", "unknown")
        severity = "HIGH" if status == "invented" else "LOW"
        emit_finding(
            session_id, turn_id,
            finding_type="suspicious_cli_flag",
            severity=severity,
            detail=f"flag='{flag}' status={status}"
        )


def emit_hallucination_findings(session_id, turn_id, halluc_result):
    for f in halluc_result.get("findings", []):
        emit_finding(
            session_id, turn_id,
            finding_type=f["type"],
            severity=f["severity"],
            detail=f["detail"]
        )


def emit_policy_finding(session_id, turn_id, action, alpha, reason):
    severity_map = {"INJECT": "LOW", "REGENERATE": "MEDIUM", "ROLLBACK": "HIGH"}
    severity = severity_map.get(action, "INFO")
    if action != "CONTINUE":
        emit_finding(
            session_id, turn_id,
            finding_type=f"policy_{action.lower()}",
            severity=severity,
            detail=f"alpha={alpha:.4f} reason={reason}"
        )
