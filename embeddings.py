import hashlib
import math


def _text_to_hash_vector(text, dim=64):
    tokens = text.lower().split()
    vec = [0.0] * dim
    for token in tokens:
        h = int(hashlib.md5(token.encode()).hexdigest(), 16)
        for i in range(dim):
            bit = (h >> i) & 1
            vec[i] += 1.0 if bit else -1.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def embed(text):
    return _text_to_hash_vector(text)


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
    return round(1.0 - sim, 4)


def anchor_drift(anchor_text, current_text):
    return goal_drift(anchor_text, current_text)
