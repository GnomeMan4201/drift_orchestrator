import math, os, httpx
from sqlite_store import insert_row
from utils import uid, now_iso, clamp

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://127.0.0.1:8765")
GATEWAY_TIMEOUT = float(os.getenv("GATEWAY_TIMEOUT", "180"))

def _get_embedding(text):
    try:
        r = httpx.post(f"{GATEWAY_URL}/embed",
            json={"text": text, "caller": "drift_orchestrator.embedding_evaluator"},
            timeout=GATEWAY_TIMEOUT)
        r.raise_for_status()
        return r.json()["embedding"]
    except httpx.ConnectError:
        raise RuntimeError(f"localai_gateway not reachable at {GATEWAY_URL}")
    except Exception as e:
        raise RuntimeError(f"Embedding request failed: {e}")

def _cosine(a, b):
    dot = sum(x*y for x,y in zip(a,b))
    na = math.sqrt(sum(x*x for x in a))
    nb = math.sqrt(sum(x*x for x in b))
    return 0.0 if na==0 or nb==0 else dot/(na*nb)

def embed_distance(text_a, text_b):
    return round(1.0 - _cosine(_get_embedding(text_a), _get_embedding(text_b)), 4)

def evaluate_embedding(window_text, anchor_text, goal_text, session_id, branch_id, window_index, turn_index, alpha):
    if not anchor_text or not window_text:
        return None
    anchor_dist = embed_distance(anchor_text, window_text)
    goal_dist = embed_distance(goal_text, window_text) if goal_text else anchor_dist
    embed_score = clamp(round((anchor_dist + goal_dist) / 2, 4))
    insert_row("embedding_eval", {"id": uid(), "session_id": session_id, "branch_id": branch_id, "window_index": window_index, "turn_index": turn_index, "alpha": alpha, "anchor_dist": anchor_dist, "goal_dist": goal_dist, "embed_score": embed_score, "created_at": now_iso()})
    print("[EMBED] window={} anchor_dist={:.4f} goal_dist={:.4f} embed_score={:.4f}".format(window_index, anchor_dist, goal_dist, embed_score))
    return embed_score
