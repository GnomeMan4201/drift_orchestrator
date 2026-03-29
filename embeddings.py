import math
import os
import hashlib
import sqlite3
import json
import threading

_model = None
_model_name = None
_use_stub = False
_model_lock = threading.Lock()
_cache_conn = None
_cache_lock = threading.Lock()
_config = None

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "embed_cache.db")


def _get_config():
    global _config
    if _config is None:
        try:
            from embed_config import load_config
            _config = load_config()
        except Exception:
            _config = {
                "model_name": "all-MiniLM-L6-v2",
                "cache_enabled": True,
                "fallback_to_stub": True,
                "normalize": True,
                "device": "cpu",
                "cache_max_entries": 10000,
            }
    return _config


def _get_cache():
    global _cache_conn
    if _cache_conn is not None:
        return _cache_conn
    cfg = _get_config()
    if not cfg.get("cache_enabled", True):
        return None
    with _cache_lock:
        if _cache_conn is not None:
            return _cache_conn
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS embed_cache (
                text_hash TEXT PRIMARY KEY,
                model_name TEXT NOT NULL,
                vector TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_model ON embed_cache(model_name)")
        conn.commit()
        _cache_conn = conn
    return _cache_conn


def _cache_get(text_hash, model_name):
    conn = _get_cache()
    if conn is None:
        return None
    try:
        with _cache_lock:
            row = conn.execute(
                "SELECT vector FROM embed_cache WHERE text_hash = ? AND model_name = ?",
                (text_hash, model_name)
            ).fetchone()
        if row:
            return json.loads(row[0])
    except Exception:
        pass
    return None


def _cache_set(text_hash, model_name, vector):
    conn = _get_cache()
    if conn is None:
        return
    cfg = _get_config()
    try:
        with _cache_lock:
            from datetime import datetime, timezone
            conn.execute(
                "INSERT OR REPLACE INTO embed_cache (text_hash, model_name, vector, created_at) VALUES (?, ?, ?, ?)",
                (text_hash, model_name, json.dumps(vector), datetime.now(timezone.utc).isoformat())
            )
            conn.commit()
            count = conn.execute("SELECT COUNT(*) FROM embed_cache").fetchone()[0]
            max_entries = cfg.get("cache_max_entries", 10000)
            if count > max_entries:
                conn.execute("""
                    DELETE FROM embed_cache WHERE text_hash IN (
                        SELECT text_hash FROM embed_cache
                        ORDER BY created_at ASC
                        LIMIT ?
                    )
                """, (count - max_entries,))
                conn.commit()
    except Exception:
        pass


def _text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _get_model():
    global _model, _model_name, _use_stub
    cfg = _get_config()
    target_model = cfg.get("model_name", "all-MiniLM-L6-v2")

    if _model is not None and _model_name == target_model:
        return _model

    with _model_lock:
        if _model is not None and _model_name == target_model:
            return _model
        try:
            from sentence_transformers import SentenceTransformer
            device = cfg.get("device", "cpu")
            _model = SentenceTransformer(target_model, device=device)
            _model_name = target_model
            _use_stub = False
        except Exception:
            if cfg.get("fallback_to_stub", True):
                _use_stub = True
                _model = None
                _model_name = target_model
            else:
                raise
    return _model


def embed(text):
    if not text or not text.strip():
        cfg = _get_config()
        dim = 384 if not _use_stub else 64
        return [0.0] * dim

    cfg = _get_config()
    model_name = cfg.get("model_name", "all-MiniLM-L6-v2")
    text_hash = _text_hash(text)

    cached = _cache_get(text_hash, model_name)
    if cached is not None:
        return cached

    model = _get_model()

    if _use_stub or model is None:
        vec = _stub_embed(text)
    else:
        try:
            normalize = cfg.get("normalize", True)
            vec = model.encode(text, normalize_embeddings=normalize).tolist()
        except Exception:
            vec = _stub_embed(text)

    _cache_set(text_hash, model_name, vec)
    return vec


def _stub_embed(text, dim=64):
    tokens = text.lower().split()
    vec = [0.0] * dim
    for token in tokens:
        h = int(hashlib.md5(token.encode()).hexdigest(), 16)
        for i in range(dim):
            bit = (h >> i) & 1
            vec[i] += 1.0 if bit else -1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def cosine_similarity(v1, v2):
    if not v1 or not v2:
        return 0.0
    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = math.sqrt(sum(a * a for a in v1)) or 1.0
    n2 = math.sqrt(sum(b * b for b in v2)) or 1.0
    return round(dot / (n1 * n2), 4)


def goal_drift(anchor_text, current_text):
    v1 = embed(anchor_text)
    v2 = embed(current_text)
    sim = cosine_similarity(v1, v2)
    return round(max(0.0, min(1.0, 1.0 - sim)), 4)


def anchor_drift(anchor_text, current_text):
    return goal_drift(anchor_text, current_text)


def get_backend():
    _get_model()
    cfg = _get_config()
    model_name = cfg.get("model_name", "all-MiniLM-L6-v2")
    if _use_stub:
        return f"stub (fallback from {model_name})"
    return f"sentence-transformers:{model_name}"


def cache_stats():
    conn = _get_cache()
    if conn is None:
        return {"enabled": False}
    try:
        with _cache_lock:
            total = conn.execute("SELECT COUNT(*) FROM embed_cache").fetchone()[0]
            models = conn.execute(
                "SELECT model_name, COUNT(*) FROM embed_cache GROUP BY model_name"
            ).fetchall()
        return {
            "enabled": True,
            "total_entries": total,
            "by_model": {m: c for m, c in models},
            "db_path": DB_PATH
        }
    except Exception:
        return {"enabled": True, "total_entries": 0}


def warm_cache(texts):
    print(f"  [CACHE] warming {len(texts)} embeddings...")
    for i, text in enumerate(texts):
        embed(text)
        if (i + 1) % 10 == 0:
            print(f"  [CACHE] {i + 1}/{len(texts)}")
    stats = cache_stats()
    print(f"  [CACHE] done — {stats['total_entries']} total entries cached")
    return stats
