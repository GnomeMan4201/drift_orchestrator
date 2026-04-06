from __future__ import annotations
import json
import math
from pathlib import Path
from typing import Any

import httpx

OLLAMA_BASE = "http://127.0.0.1:11434"
EMBED_MODEL = "nomic-embed-text:latest"
VAULT_DIR = Path.home() / ".cache" / "drift_orchestrator" / "semantic_vault"
VAULT_DIR.mkdir(parents=True, exist_ok=True)

def _vault_path(agent: str) -> Path:
    return VAULT_DIR / f"{agent}.json"

def _load(agent: str) -> list[dict[str, Any]]:
    p = _vault_path(agent)
    if not p.exists():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []

def _save(agent: str, rows: list[dict[str, Any]]) -> None:
    _vault_path(agent).write_text(json.dumps(rows[-200:], indent=2), encoding="utf-8")

def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)

def _embed_text(text: str) -> list[float]:
    text = (text or "").strip()
    if not text:
        return []

    with httpx.Client(timeout=90.0) as client:
        try:
            r = client.post(
                f"{OLLAMA_BASE}/api/embed",
                json={"model": EMBED_MODEL, "input": text},
            )
            r.raise_for_status()
            data = r.json()
            embeds = data.get("embeddings") or []
            if embeds and isinstance(embeds[0], list):
                return [float(x) for x in embeds[0]]
        except Exception:
            pass

        r = client.post(
            f"{OLLAMA_BASE}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": text},
        )
        r.raise_for_status()
        data = r.json()
        emb = data.get("embedding") or []
        return [float(x) for x in emb]

def add_semantic_checkpoint(
    agent: str,
    prompt: str,
    response: str,
    inj_score: float,
    drift_score: float,
    posture_name: str | None = None,
    state_vector: dict[str, Any] | None = None,
) -> None:
    rows = _load(agent)
    prompt_emb = _embed_text(prompt)
    response_emb = _embed_text(response[:4000])

    rows.append({
        "prompt": prompt,
        "response": response,
        "inj_score": float(inj_score),
        "drift_score": float(drift_score),
        "posture_name": posture_name,
        "state_vector": state_vector or {},
        "prompt_embedding": prompt_emb,
        "response_embedding": response_emb,
    })
    _save(agent, rows)

def get_semantic_rollback(
    agent: str,
    prompt: str,
    posture_name: str | None = None,
    state_vector: dict[str, Any] | None = None,
    min_score: float = 0.25,
) -> str | None:
    rows = _load(agent)
    if not rows:
        return None

    query_emb = _embed_text(prompt)
    best = None
    best_score = -1.0

    for row in rows:
        score = 0.0
        cand_emb = row.get("prompt_embedding") or []
        score += 0.80 * _cosine(query_emb, cand_emb)

        if posture_name and row.get("posture_name") == posture_name:
            score += 0.15

        cur_state = state_vector or {}
        prev_state = row.get("state_vector") or {}
        if cur_state and prev_state:
            keys = ("host_risk", "network_restrictiveness", "tool_trust", "anomaly_level")
            diffs = []
            for k in keys:
                try:
                    diffs.append(abs(float(cur_state.get(k, 0.0)) - float(prev_state.get(k, 0.0))))
                except Exception:
                    diffs.append(1.0)
            score += 0.05 * (1.0 - (sum(diffs) / len(diffs)))

        if score > best_score:
            best_score = score
            best = row

    if best and best_score >= min_score:
        return str(best.get("response") or "")

    return str(rows[-1].get("response") or "") if rows else None
