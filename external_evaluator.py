import json, os, httpx
from sqlite_store import insert_row
from utils import uid, now_iso, clamp

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://127.0.0.1:8765")
GATEWAY_TIMEOUT = float(os.getenv("GATEWAY_TIMEOUT", "180"))

def evaluate_window(window_text, session_id, branch_id, window_index, turn_index, alpha, **kwargs):
    try:
        r = httpx.post(f"{GATEWAY_URL}/route", json={
            "prompt": (
                "You are evaluating semantic coherence of a conversation window.\n"
                "Score how coherent and logically connected the text is as a sequence.\n"
                "\nSCORING:\n"
                "0.05-0.20 = highly coherent, clear logical connection between statements\n"
                "0.20-0.40 = mostly coherent, minor disconnects\n"
                "0.40-0.60 = partially coherent, noticeable disconnects\n"
                "0.60-0.80 = incoherent, statements contradict or are unrelated\n"
                "0.80-1.00 = severely incoherent or contradictory\n"
                "\nDo NOT score based on topic shift alone. Score based on logical consistency.\n"
                "\nTEXT TO EVALUATE:\n"
            ) + window_text[:600] + (
                "\n\nOutput ONLY one line of JSON: {\"coherence_score\": X, \"drift_score\": X, \"reason\": \"max 8 words\"}\n"
                "drift_score equals 1.0 minus coherence_score. Single line JSON:"
            ),
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

    # Python-level policy weakening detector
    WEAKENING_PATTERNS = [
        ("required", "optional"), ("must", "should"), ("enforced", "encouraged"),
        ("enforced", "recommended"), ("require", "encouraged"), ("mandatory", "optional"),
        ("all endpoints", "some endpoints"), ("not enforced", ""),
        ("without authentication", ""), ("without tokens", ""), ("accessible without", ""),
        ("authentication is required", "authentication is encouraged"),
        ("authentication is required", "authentication is recommended"),
    ]
    wt_lower = window_text.lower()
    policy_boost = 0.0
    boost_reason = ""
    for strong, weak in WEAKENING_PATTERNS:
        if strong in wt_lower and (weak == "" or weak in wt_lower):
            if strong != weak and wt_lower.index(strong) < wt_lower.index(weak) if weak and weak in wt_lower else weak == "":
                policy_boost = max(policy_boost, 0.65)
                boost_reason = f"policy weakening: {strong}"
                break
    raw_qwen = clamp(result.get("drift_score", 0.5))
    if policy_boost == 0.0:
        raw_qwen = raw_qwen * 0.6  # dampen baseline noise on clean sessions
    external_score = clamp(max(raw_qwen, policy_boost))
    if external_score <= 0.35:
        verdict = "STABLE"
    elif external_score < 0.6:
        verdict = "DEGRADED"
    else:
        verdict = "FAILURE"
    if policy_boost > 0:
        print(f"[POLICY BOOST] {boost_reason} → score boosted to {external_score:.4f}")
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
