import json, os, httpx
from sqlite_store import insert_row
from utils import uid, now_iso, clamp

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://127.0.0.1:8765")
GATEWAY_TIMEOUT = float(os.getenv("GATEWAY_TIMEOUT", "180"))

def evaluate_window(window_text, session_id, branch_id, window_index, turn_index, alpha, **kwargs):
    try:
        r = httpx.post(f"{GATEWAY_URL}/route", json={
            "prompt": "Analyze the semantic transition in this text. Does it maintain logical flow?\n\nTEXT:\n" + window_text[:400] + "\n\nOutput ONLY one line of JSON (no newlines inside): {\"coherence_score\": X, \"drift_score\": X, \"verdict\": \"STABLE|DEGRADED|FAILURE\", \"reason\": \"max 8 words\"}\nReplace X with floats 0.0-1.0. Single line. JSON:",
            "tier": "reasoning",
            "caller": "drift_orchestrator.external_evaluator",
            "stream": False,
            "options": {"num_predict": 512, "temperature": 0.1}
        }, timeout=GATEWAY_TIMEOUT)
        r.raise_for_status()
        text = r.json().get("response", "").strip()
    except httpx.ConnectError:
        print("[EXTERNAL] localai_gateway not reachable — skipping external eval")
        return None
    except Exception as e:
        print(f"[EXTERNAL] Failed: {e}")
        return None

    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        try:
            result = json.loads(text.replace("```json","").replace("```","").strip())
        except:
            print(f"[EXTERNAL] Could not parse: {text[:80]}")
            return None

    external_score = clamp(result.get("drift_score", 0.5))
    verdict = result.get("verdict", "UNKNOWN")
    divergence = round(abs(alpha - external_score), 4)
    insert_row("external_eval", {"id": uid(), "session_id": session_id, "branch_id": branch_id,
        "window_index": window_index, "turn_index": turn_index, "alpha": alpha,
        "external_score": external_score, "verdict": verdict,
        "divergence": divergence, "raw_response": json.dumps(result), "created_at": now_iso()})
    print("[EXTERNAL] window={} alpha={:.4f} external={:.4f} divergence={:.4f} verdict={}".format(
        window_index, alpha, external_score, divergence, verdict))
    if divergence >= 0.30:
        print("[DIVERGENCE WARNING] Internal and external signals disagree significantly")
        print("[DIVERGENCE] Reason: {}".format(result.get("reason", "unknown")))
    return result
