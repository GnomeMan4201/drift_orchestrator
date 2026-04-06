#!/usr/bin/env python3
import json
import time
from pathlib import Path
from typing import Any

LOG_PATH = Path("results/trace_log.jsonl")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

def log_event(event: dict[str, Any]) -> None:
    event = dict(event)
    event.setdefault("ts", time.time())
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
