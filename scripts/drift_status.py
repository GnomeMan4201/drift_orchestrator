#!/usr/bin/env python3
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "drift.db"
EMBED_CACHE_PATH = DATA_DIR / "embed_cache.db"
LOGS_DIR = ROOT / "logs"
SESSIONS_DIR = ROOT / "sessions"


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def scalar(conn: sqlite3.Connection, query: str, params: tuple = ()) -> int:
    row = conn.execute(query, params).fetchone()
    if not row:
        return 0
    value = row[0]
    return int(value) if value is not None else 0


def fetch_one_dict(conn: sqlite3.Connection, query: str, params: tuple = ()) -> dict | None:
    cur = conn.execute(query, params)
    row = cur.fetchone()
    if row is None:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))


def safe_recent_file_info(path: Path) -> str:
    if not path.exists():
        return "missing"
    stat = path.stat()
    return f"{path.name} ({stat.st_size} bytes)"


def main() -> int:
    print("# drift_orchestrator status")
    print(f"# root: {ROOT}")
    print(f"# data_dir: {DATA_DIR}")
    print(f"# db: {DB_PATH}")
    print(f"# embed_cache: {EMBED_CACHE_PATH}")
    print(f"# logs_dir: {LOGS_DIR}")
    print(f"# sessions_dir: {SESSIONS_DIR}")

    print("# files:")
    print(f"#   - {safe_recent_file_info(DB_PATH)}")
    print(f"#   - {safe_recent_file_info(EMBED_CACHE_PATH)}")

    if not DB_PATH.exists():
        print("# database: missing")
        return 0

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
    except Exception as e:
        print(f"# database_open_error: {e}")
        return 1

    try:
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        ]
        print("# tables:")
        for name in tables:
            print(f"#   - {name}")

        table_counts: dict[str, int] = {}
        for name in tables:
            try:
                table_counts[name] = scalar(conn, f'SELECT COUNT(*) FROM "{name}"')
            except Exception:
                table_counts[name] = -1

        print("# row_counts:")
        for name, count in table_counts.items():
            if count >= 0:
                print(f"#   - {name}: {count}")
            else:
                print(f"#   - {name}: unavailable")

        recent_session = None
        for query in (
            "SELECT * FROM sessions ORDER BY created_at DESC LIMIT 1",
            "SELECT * FROM sessions ORDER BY id DESC LIMIT 1",
        ):
            if table_exists(conn, "sessions"):
                try:
                    recent_session = fetch_one_dict(conn, query)
                    if recent_session:
                        break
                except Exception:
                    pass

        if recent_session:
            print("# latest_session:")
            for k, v in recent_session.items():
                print(f"#   - {k}: {v}")
        else:
            print("# latest_session: none")

        recent_turn = None
        for table_name in ("turn_metrics", "turns"):
            if not table_exists(conn, table_name):
                continue
            for query in (
                f'SELECT * FROM "{table_name}" ORDER BY created_at DESC LIMIT 1',
                f'SELECT * FROM "{table_name}" ORDER BY id DESC LIMIT 1',
            ):
                try:
                    recent_turn = fetch_one_dict(conn, query)
                    if recent_turn:
                        break
                except Exception:
                    pass
            if recent_turn:
                break

        if recent_turn:
            print("# latest_turn_record:")
            for k, v in recent_turn.items():
                print(f"#   - {k}: {v}")
        else:
            print("# latest_turn_record: none")

        summary = {
            "db_exists": True,
            "table_count": len(tables),
            "session_rows": table_counts.get("sessions", 0),
            "turn_metric_rows": table_counts.get("turn_metrics", 0),
            "finding_rows": table_counts.get("findings", 0),
            "policy_event_rows": table_counts.get("policy_events", 0),
        }
        print("# summary_json:")
        print(json.dumps(summary, indent=2, sort_keys=True))

    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
