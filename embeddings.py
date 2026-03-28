import math
import os

_model = None
_model_name = "all-MiniLM-L6-v2"
_use_stub = False


def _get_model():
    global _model, _use_stub
    if _model is not None:
        return _model
    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(_model_name)
        _use_stub = False
    except Exception:
        _use_stub = True
        _model = None
    return _model


def embed(text):
    model = _get_model()
    if _use_stub or model is None:
        return _stub_embed(text)
    try:
        vec = model.encode(text, normalize_embeddings=True).tolist()
        return vec
    except Exception:
        return _stub_embed(text)


def _stub_embed(text, dim=64):
    import hashlib
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
    return "stub" if _use_stub else f"sentence-transformers:{_model_name}"
