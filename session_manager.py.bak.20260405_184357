import uuid
from datetime import datetime, timezone
import json
from sqlite_store import insert_row, fetch_rows, fetch_one, init_db


def _now():
    return datetime.now(timezone.utc).isoformat()


def _uid():
    return str(uuid.uuid4())


def create_session(meta=None):
    init_db()
    sid = _uid()
    insert_row("sessions", {
        "id": sid,
        "created_at": _now(),
        "meta": json.dumps(meta or {})
    })
    branch_id = create_branch(sid, label="main")
    return sid, branch_id


def create_branch(session_id, parent_branch_id=None, label=None):
    bid = _uid()
    insert_row("branches", {
        "id": bid,
        "session_id": session_id,
        "parent_branch_id": parent_branch_id or "",
        "created_at": _now(),
        "label": label or ""
    })
    return bid


def append_turn(session_id, branch_id, role, content, token_count=None):
    existing = fetch_rows(
        "turns",
        "branch_id = ? AND session_id = ?",
        [branch_id, session_id]
    )
    turn_index = len(existing)
    tid = _uid()
    if token_count is None:
        token_count = len(content.split())
    insert_row("turns", {
        "id": tid,
        "branch_id": branch_id,
        "session_id": session_id,
        "turn_index": turn_index,
        "role": role,
        "content": content,
        "token_count": token_count,
        "created_at": _now()
    })
    return tid, turn_index


def create_checkpoint(session_id, branch_id, turn_index, status="green", snapshot=None):
    cid = _uid()
    insert_row("checkpoints", {
        "id": cid,
        "branch_id": branch_id,
        "session_id": session_id,
        "turn_index": turn_index,
        "status": status,
        "snapshot": json.dumps(snapshot or {}),
        "created_at": _now()
    })
    return cid


def get_last_green_checkpoint(session_id, branch_id):
    rows = fetch_rows(
        "checkpoints",
        "session_id = ? AND branch_id = ? AND status = ? ORDER BY turn_index DESC",
        [session_id, branch_id, "green"]
    )
    return rows[0] if rows else None


def restore_checkpoint(session_id, branch_id, checkpoint_id):
    cp = fetch_one("checkpoints", "id = ?", [checkpoint_id])
    if not cp:
        raise ValueError(f"Checkpoint {checkpoint_id} not found")
    restore_turn_index = cp["turn_index"]
    turns = fetch_rows(
        "turns",
        "session_id = ? AND branch_id = ? AND turn_index > ?",
        [session_id, branch_id, restore_turn_index]
    )
    new_branch_id = create_branch(session_id, parent_branch_id=branch_id, label=f"restore@{restore_turn_index}")
    kept_turns = fetch_rows(
        "turns",
        "session_id = ? AND branch_id = ? AND turn_index <= ? ORDER BY turn_index ASC",
        [session_id, branch_id, restore_turn_index]
    )
    for t in kept_turns:
        tid = _uid()
        insert_row("turns", {
            "id": tid,
            "branch_id": new_branch_id,
            "session_id": session_id,
            "turn_index": t["turn_index"],
            "role": t["role"],
            "content": t["content"],
            "token_count": t["token_count"],
            "created_at": _now()
        })
    return new_branch_id, restore_turn_index, len(turns)
