import math
from sentence_transformers import SentenceTransformer
from sqlite_store import insert_row
from utils import uid, now_iso, clamp

_model = None

def _get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model

def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na  = math.sqrt(sum(x * x for x in a))
    nb  = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)

def embed_distance(text_a, text_b):
    model = _get_model()
    ea, eb = model.encode([text_a, text_b])
    sim = _cosine(ea.tolist(), eb.tolist())
    return round(1.0 - sim, 4)

def evaluate_embedding(window_text, anchor_text, goal_text,
                       session_id, branch_id, window_index, turn_index, alpha):
    if not anchor_text or not window_text:
        return None

    anchor_dist = embed_distance(anchor_text, window_text)
    goal_dist   = embed_distance(goal_text, window_text) if goal_text else anchor_dist
    embed_score = clamp(round((anchor_dist + goal_dist) / 2, 4))

    insert_row("embedding_eval", {
        "id": uid(),
        "session_id": session_id,
        "branch_id": branch_id,
        "window_index": window_index,
        "turn_index": turn_index,
        "alpha": alpha,
        "anchor_dist": anchor_dist,
        "goal_dist": goal_dist,
        "embed_score": embed_score,
        "created_at": now_iso()
    })

    print("[EMBED] window={} anchor_dist={:.4f} goal_dist={:.4f} embed_score={:.4f}".format(
        window_index, anchor_dist, goal_dist, embed_score))

    return embed_score
