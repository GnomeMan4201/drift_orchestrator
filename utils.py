import json
import os
import uuid
from datetime import datetime, timezone


def load_jsonl(path):
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def save_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


def uid():
    return str(uuid.uuid4())


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def clamp(value, lo=0.0, hi=1.0):
    return max(lo, min(hi, value))


def weighted_average(values_weights):
    total_w = sum(w for _, w in values_weights)
    if total_w == 0:
        return 0.0
    return sum(v * w for v, w in values_weights) / total_w
