import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "drift.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            meta TEXT
        );

        CREATE TABLE IF NOT EXISTS branches (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            parent_branch_id TEXT,
            created_at TEXT NOT NULL,
            label TEXT,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );

        CREATE TABLE IF NOT EXISTS turns (
            id TEXT PRIMARY KEY,
            branch_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            turn_index INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            token_count INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (branch_id) REFERENCES branches(id)
        );

        CREATE TABLE IF NOT EXISTS checkpoints (
            id TEXT PRIMARY KEY,
            branch_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            turn_index INTEGER NOT NULL,
            status TEXT NOT NULL,
            snapshot TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (branch_id) REFERENCES branches(id)
        );

        CREATE TABLE IF NOT EXISTS turn_metrics (
            id TEXT PRIMARY KEY,
            turn_id TEXT NOT NULL,
            branch_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            turn_index INTEGER NOT NULL,
            window_index INTEGER NOT NULL,
            rho_density REAL,
            d_goal REAL,
            d_anchor REAL,
            risk_verify REAL,
            repetition_score REAL,
            alpha REAL,
            raw_scores TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (turn_id) REFERENCES turns(id)
        );

        CREATE TABLE IF NOT EXISTS findings (
            id TEXT PRIMARY KEY,
            turn_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            finding_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            detail TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (turn_id) REFERENCES turns(id)
        );

        CREATE TABLE IF NOT EXISTS policy_events (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            branch_id TEXT NOT NULL,
            turn_index INTEGER NOT NULL,
            alpha REAL,
            action TEXT NOT NULL,
            level INTEGER DEFAULT 0,
            reason TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );

        CREATE TABLE IF NOT EXISTS external_eval (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            branch_id TEXT NOT NULL,
            window_index INTEGER NOT NULL,
            turn_index INTEGER NOT NULL,
            alpha REAL,
            external_score REAL,
            verdict TEXT,
            divergence REAL,
            raw_response TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );
    """)
    conn.commit()
    conn.close()


def insert_row(table, row_dict):
    conn = get_connection()
    c = conn.cursor()
    cols = ", ".join(row_dict.keys())
    placeholders = ", ".join(["?" for _ in row_dict])
    c.execute(f"INSERT INTO {table} ({cols}) VALUES ({placeholders})", list(row_dict.values()))
    conn.commit()
    conn.close()


def fetch_rows(table, where_clause="", params=None):
    conn = get_connection()
    c = conn.cursor()
    sql = f"SELECT * FROM {table}"
    if where_clause:
        sql += f" WHERE {where_clause}"
    c.execute(sql, params or [])
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def fetch_one(table, where_clause="", params=None):
    rows = fetch_rows(table, where_clause, params)
    return rows[0] if rows else None
