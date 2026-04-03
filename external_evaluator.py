import os
import json
import urllib.request
import urllib.error
from utils import uid, now_iso, clamp
from sqlite_store import insert_row

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_URL = "https://api.anthropic.com/v1/messages"

SYSTEM_PROMPT = """You are an external coherence evaluator for LLM agent sessions.
You will be given a window of agent output text.
Score the coherence, consistency, and reasoning quality from 0.0 (complete failure) to 1.0 (fully coherent).
A high drift score means the output is incoherent, contradictory, or degraded.

Respond ONLY with valid JSON, no preamble, no markdown:
{
  "coherence_score": <float 0.0-1.0>,
  "drift_score": <float 0.0-1.0>,
  "verdict": "STABLE" | "DEGRADED" | "FAILURE",
  "reason": "<one sentence>"
}"""


def evaluate_window(window_text, session_id, branch_id, window_index, turn_index, alpha):
    if not ANTHROPIC_API_KEY:
        print("[EXTERNAL] No API key set - skipping external eval")
        return None

    payload = json.dumps({
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 256,
        "system": SYSTEM_PROMPT,
        "messages": [
            {"role": "user", "content": "Evaluate this agent output window:\n\n" + window_text}
        ]
    }).encode("utf-8")

    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
            text = raw["content"][0]["text"].strip()
            result = json.loads(text)
    except urllib.error.HTTPError as e:
        print("[EXTERNAL] API error: {} {}".format(e.code, e.reason))
        return None
    except Exception as e:
        print("[EXTERNAL] Failed: {}".format(e))
        return None

    external_score = clamp(result.get("drift_score", 0.5))
    verdict = result.get("verdict", "UNKNOWN")
    divergence = round(abs(alpha - external_score), 4)

    insert_row("external_eval", {
        "id": uid(),
        "session_id": session_id,
        "branch_id": branch_id,
        "window_index": window_index,
        "turn_index": turn_index,
        "alpha": alpha,
        "external_score": external_score,
        "verdict": verdict,
        "divergence": divergence,
        "raw_response": json.dumps(result),
        "created_at": now_iso()
    })

    print("[EXTERNAL] window={} alpha={:.4f} external={:.4f} divergence={:.4f} verdict={}".format(
        window_index, alpha, external_score, divergence, verdict))

    if divergence >= 0.30:
        print("[DIVERGENCE WARNING] Internal and external signals disagree significantly")
        print("[DIVERGENCE] Reason: {}".format(result.get("reason", "unknown")))

    return result
