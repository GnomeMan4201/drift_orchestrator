import math
import re
from collections import Counter


def count_tokens(text):
    return len(text.split())


def sliding_token_windows(turns, window_size=5, step=1):
    windows = []
    for i in range(0, max(1, len(turns) - window_size + 1), step):
        window = turns[i:i + window_size]
        windows.append((i, window))
    return windows


def _entropy(text):
    tokens = text.lower().split()
    if not tokens:
        return 0.0
    counts = Counter(tokens)
    total = len(tokens)
    ent = -sum((c / total) * math.log2(c / total) for c in counts.values())
    return ent


def _type_token_ratio(text):
    tokens = text.lower().split()
    if not tokens:
        return 0.0
    return len(set(tokens)) / len(tokens)


def _avg_sentence_length(text):
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return 0.0
    lengths = [len(s.split()) for s in sentences]
    return sum(lengths) / len(lengths)


def _code_density(text):
    code_markers = len(re.findall(r'```|def |class |import |return |->|:=|\bif\b|\bfor\b|\bwhile\b', text))
    tokens = max(1, len(text.split()))
    return min(1.0, code_markers / tokens)


class CompositeDensityScorer:
    def __init__(self, weights=None):
        self.weights = weights or {
            "entropy": 0.30,
            "ttr": 0.25,
            "avg_sent_len": 0.20,
            "code_density": 0.25,
        }

    def score(self, texts):
        combined = " ".join(texts)
        if not combined.strip():
            return 0.0, {}

        raw_entropy = _entropy(combined)
        max_entropy = math.log2(max(1, len(set(combined.lower().split()))))
        norm_entropy = raw_entropy / max_entropy if max_entropy > 0 else 0.0

        ttr = _type_token_ratio(combined)

        avg_sl = _avg_sentence_length(combined)
        norm_sl = min(1.0, avg_sl / 40.0)

        code_d = _code_density(combined)

        breakdown = {
            "entropy": round(norm_entropy, 4),
            "ttr": round(ttr, 4),
            "avg_sent_len": round(norm_sl, 4),
            "code_density": round(code_d, 4),
        }

        density = sum(self.weights[k] * breakdown[k] for k in self.weights)
        return round(density, 4), breakdown


def compute_repetition_score(texts):
    all_tokens = []
    for t in texts:
        all_tokens.extend(t.lower().split())
    if not all_tokens:
        return 0.0
    counts = Counter(all_tokens)
    total = len(all_tokens)
    repeated = sum(c for c in counts.values() if c > 1)
    return round(repeated / total, 4)
