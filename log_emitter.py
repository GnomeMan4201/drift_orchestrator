import json
import time
from utils import uid, now_iso

WINDOW_SIZE = 4
WINDOW_STRIDE = 1
WINDOW_TYPE = "sliding"

def _norm(value, lo=0.0, hi=1.0):
    if value is None:
        return None
    return round(max(0.0, min(1.0, (value - lo) / (hi - lo))), 4)

def emit_session_record(session_id, model, input_source, outfile):
    record = {
        "record_type": "session",
        "session_id": session_id,
        "input_source": input_source,
        "model": model,
        "timestamp_start": now_iso(),
        "window_size": WINDOW_SIZE,
        "window_stride": WINDOW_STRIDE,
        "window_type": WINDOW_TYPE
    }
    outfile.write(json.dumps(record) + "\n")
    return record

def emit_window_record(session_id, window_index, turn_index,
                       internal_score_raw, external_score_raw,
                       embed_score, verdict,
                       internal_triggered, external_triggered,
                       rollback_flag, session_start_ms, outfile):

    internal_norm = _norm(internal_score_raw)
    external_norm = _norm(external_score_raw)
    divergence = round(abs(internal_norm - external_norm), 4) if (internal_norm is not None and external_norm is not None) else None
    now_ms = int(time.time() * 1000)
    elapsed_ms = now_ms - session_start_ms

    record = {
        "record_type": "window",
        "session_id": session_id,
        "window_index": window_index,
        "turn_index": turn_index,
        "time_since_session_start_ms": elapsed_ms,
        "internal_score_raw": internal_score_raw,
        "external_score_raw": external_score_raw,
        "internal_score_norm": internal_norm,
        "external_score_norm": external_norm,
        "divergence": divergence,
        "embed_score": embed_score,
        "internal_triggered": internal_triggered,
        "external_triggered": external_triggered,
        "verdict": verdict,
        "first_failure_flag": verdict in ("DEGRADED", "FAILURE"),
        "rollback_flag": rollback_flag,
        "timestamp": now_iso()
    }
    outfile.write(json.dumps(record) + "\n")
    return record

def emit_event_record(session_id, window_index, event_type,
                      trigger_source, trigger_metric, reason, outfile):
    record = {
        "record_type": "event",
        "session_id": session_id,
        "window_index": window_index,
        "event_type": event_type,
        "trigger_source": trigger_source,
        "trigger_metric": trigger_metric,
        "reason": reason,
        "timestamp": now_iso()
    }
    outfile.write(json.dumps(record) + "\n")
    return record
