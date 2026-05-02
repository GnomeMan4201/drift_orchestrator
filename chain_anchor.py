"""
chain_anchor.py — Chain-scoped anchor storage for cross-model campaign runs.

Stores a named anchor embedding once at chain start.
All sub-chain sessions retrieve it by chain_id instead of deriving
their anchor from their own first message.

Usage:
    # At chain start (once):
    from chain_anchor import register_chain_anchor, get_chain_anchor_text

    register_chain_anchor(
        chain_id="CC09_RUN_001",
        anchor_text="Sensitive user data may only be accessed by..."
    )

    # When initializing each sub-chain session:
    anchor = get_chain_anchor_text("CC09_RUN_001")
    agent = AgentRuntime(anchor_text=anchor, ...)

    # To measure drift against chain anchor directly:
    from chain_anchor import chain_anchor_drift
    delta = chain_anchor_drift("CC09_RUN_001", current_text)

Integrates with existing embed_cache.db — no new dependencies.
"""

import os
import json
import sqlite3
import threading
from datetime import datetime, timezone

from embeddings import embed, cosine_similarity

_DB_PATH = os.path.join(os.path.dirname(__file__), "data", "chain_anchors.db")
_lock = threading.Lock()
_conn = None


def _get_conn():
    global _conn
    if _conn is not None:
        return _conn
    with _lock:
        if _conn is not None:
            return _conn
        os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
        conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chain_anchors (
                chain_id    TEXT PRIMARY KEY,
                anchor_text TEXT NOT NULL,
                embedding   TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                meta        TEXT
            )
        """)
        conn.commit()
        _conn = conn
    return _conn


def register_chain_anchor(chain_id: str, anchor_text: str, meta: dict = None) -> list:
    """
    Store a named anchor for a chain run.
    Computes and caches the embedding immediately.
    Idempotent — calling again with same chain_id updates the record.

    Returns the anchor embedding vector.
    """
    embedding = embed(anchor_text)
    conn = _get_conn()
    with _lock:
        conn.execute("""
            INSERT OR REPLACE INTO chain_anchors
                (chain_id, anchor_text, embedding, created_at, meta)
            VALUES (?, ?, ?, ?, ?)
        """, (
            chain_id,
            anchor_text,
            json.dumps(embedding),
            datetime.now(timezone.utc).isoformat(),
            json.dumps(meta) if meta else None,
        ))
        conn.commit()
    print(f"[chain_anchor] registered anchor for chain '{chain_id}' "
          f"({len(anchor_text)} chars, embedding dim={len(embedding)})")
    return embedding


def get_chain_anchor_text(chain_id: str) -> str:
    """
    Retrieve anchor text for a chain.
    Pass this as anchor_text= when initializing each sub-chain session.
    """
    row = _get_conn().execute(
        "SELECT anchor_text FROM chain_anchors WHERE chain_id = ?", (chain_id,)
    ).fetchone()
    if row is None:
        raise KeyError(f"No chain anchor registered for chain_id='{chain_id}'. "
                       f"Call register_chain_anchor() first.")
    return row[0]


def get_chain_anchor_embedding(chain_id: str) -> list:
    """
    Retrieve stored anchor embedding directly (no recompute).
    Use this when you want to skip embed() entirely.
    """
    row = _get_conn().execute(
        "SELECT embedding FROM chain_anchors WHERE chain_id = ?", (chain_id,)
    ).fetchone()
    if row is None:
        raise KeyError(f"No chain anchor registered for chain_id='{chain_id}'.")
    return json.loads(row[0])


def chain_anchor_drift(chain_id: str, current_text: str) -> float:
    """
    Compute drift between current_text and the chain anchor.
    Uses stored embedding — anchor is never recomputed.
    This is the correct function for measuring sub-chain drift against
    the chain-level anchor (not sub-chain-local first-turn anchor).

    Returns drift score 0.0 (identical) to 1.0 (maximally different).
    """
    anchor_vec = get_chain_anchor_embedding(chain_id)
    current_vec = embed(current_text)
    sim = cosine_similarity(anchor_vec, current_vec)
    return round(max(0.0, min(1.0, 1.0 - sim)), 4)


def list_chain_anchors() -> list:
    """List all registered chain anchors."""
    rows = _get_conn().execute(
        "SELECT chain_id, created_at, LENGTH(anchor_text) FROM chain_anchors ORDER BY created_at DESC"
    ).fetchall()
    return [{"chain_id": r[0], "created_at": r[1], "anchor_chars": r[2]} for r in rows]


def delete_chain_anchor(chain_id: str) -> bool:
    """Remove a chain anchor. Returns True if deleted, False if not found."""
    conn = _get_conn()
    with _lock:
        cursor = conn.execute(
            "DELETE FROM chain_anchors WHERE chain_id = ?", (chain_id,)
        )
        conn.commit()
    return cursor.rowcount > 0
