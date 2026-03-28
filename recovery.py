import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from sqlite_store import fetch_rows, fetch_one, insert_row
from session_manager import (
    create_branch, append_turn, create_checkpoint,
    get_last_green_checkpoint, restore_checkpoint
)
from utils import now_iso, uid


def get_recovery_point(session_id, branch_id):
    cp = get_last_green_checkpoint(session_id, branch_id)
    if not cp:
        return None, None, None
    turns = fetch_rows(
        "turns",
        "session_id = ? AND branch_id = ? AND turn_index <= ? ORDER BY turn_index ASC",
        [session_id, branch_id, cp["turn_index"]]
    )
    return cp, turns, cp["turn_index"]


def recover(session_id, branch_id, evaluator_fn, report=True):
    cp, turns, recovery_index = get_recovery_point(session_id, branch_id)

    if not cp:
        print("[RECOVERY] No green checkpoint found. Cannot recover.")
        return None, None

    print(f"\n[RECOVERY] Last green checkpoint: turn_index={recovery_index}")
    print(f"[RECOVERY] Restoring branch from checkpoint {cp['id'][:8]}...")

    new_branch_id, restored_at, dropped = restore_checkpoint(
        session_id, branch_id, cp["id"]
    )

    print(f"[RECOVERY] New branch: {new_branch_id[:8]}...")
    print(f"[RECOVERY] Restored to turn {restored_at}, dropped {dropped} turns")
    print(f"[RECOVERY] Continuing evaluation from turn {restored_at + 1}...\n")

    remaining_turns = fetch_rows(
        "turns",
        "session_id = ? AND branch_id = ? AND turn_index > ? ORDER BY turn_index ASC",
        [session_id, branch_id, recovery_index]
    )

    if not remaining_turns:
        print("[RECOVERY] No remaining turns to evaluate after recovery point.")
    else:
        turn_data = [{"role": t["role"], "content": t["content"]} for t in remaining_turns]
        evaluator_fn(
            session_id=session_id,
            branch_id=new_branch_id,
            turns=turn_data,
            start_index=restored_at + 1,
            report=report
        )

    return new_branch_id, restored_at


def recovery_summary(session_id):
    branches = fetch_rows("branches", "session_id = ? ORDER BY created_at ASC", [session_id])
    checkpoints = fetch_rows("checkpoints", "session_id = ? ORDER BY turn_index ASC", [session_id])
    events = fetch_rows("policy_events", "session_id = ?", [session_id])

    rollbacks = [e for e in events if e["action"] == "ROLLBACK"]
    green_cps = [c for c in checkpoints if c["status"] == "green"]

    print("\n--- RECOVERY SUMMARY ---")
    print(f"  Branches total    : {len(branches)}")
    print(f"  Green checkpoints : {len(green_cps)}")
    print(f"  Rollback events   : {len(rollbacks)}")
    if green_cps:
        last = green_cps[-1]
        print(f"  Last green turn   : {last['turn_index']} (branch {last['branch_id'][:8]}...)")
    print("------------------------\n")
