import httpx

from firewall.control_plane import (
    detect_policy_injection,
    sanitize_input,
    sanitize_output,
    is_exact_request,
    score_request,
)
from firewall.checkpoint_store import save_checkpoint, get_last_good_response
from analysis.trace_logger import log_event

GATEWAY = "http://127.0.0.1:8765"
TIMEOUT_SECONDS = 60.0

def guarded_call(prompt: str, drift_score: float = 0.0, use_rollback: bool = True, agent: str = "default"):
    original_prompt = prompt
    inj_score = float(detect_policy_injection(prompt) or 0.0)

    if inj_score > 0.2:
        prompt = sanitize_input(prompt)

    expected_exact = None
    if is_exact_request(original_prompt):
        expected_exact = original_prompt.split(":", 1)[1].strip()

    if prompt.startswith("[BLOCKED"):
        last_good = get_last_good_response(agent) if use_rollback else None
        response = last_good or prompt
        reason = "sanitizer_block_with_rollback" if last_good else "sanitizer_block"

        log_event({
            "agent": agent,
            "prompt": original_prompt,
            "inj_score": inj_score,
            "drift_score": drift_score,
            "blocked": True,
            "reason": reason,
            "output": response,
        })

        return {
            "response": response,
            "inj_score": inj_score,
            "drift_score": drift_score,
            "blocked": True,
            "reason": reason,
        }

    decision = score_request(prompt, drift_score=drift_score)
    if decision["blocked"]:
        last_good = get_last_good_response(agent) if use_rollback else None
        response = last_good or "[BLOCKED: control-plane anomaly detected]"
        reason = f'{decision["reason"]}_rollback' if last_good else decision["reason"]

        log_event({
            "agent": agent,
            "prompt": original_prompt,
            "inj_score": float(decision["inj_score"]),
            "drift_score": float(decision["drift_score"]),
            "blocked": True,
            "reason": reason,
            "output": response,
        })

        return {
            "response": response,
            "inj_score": float(decision["inj_score"]),
            "drift_score": float(decision["drift_score"]),
            "blocked": True,
            "reason": reason,
        }

    try:
        resp = httpx.post(
            f"{GATEWAY}/route",
            json={"prompt": prompt},
            timeout=TIMEOUT_SECONDS,
        )
        print("GATEWAY STATUS:", resp.status_code)
        resp.raise_for_status()
        payload = resp.json()
        out = payload.get("response", "")
        out = sanitize_output(out, expected_exact)
    except Exception as e:
        print("GATEWAY ERROR:", repr(e))
        last_good = get_last_good_response(agent) if use_rollback else None
        response = last_good or "[HTTP ERROR]"
        reason = "http_error_rollback" if last_good else "http_error"

        log_event({
            "agent": agent,
            "prompt": original_prompt,
            "inj_score": inj_score,
            "drift_score": drift_score,
            "blocked": True,
            "reason": reason,
            "output": response,
        })

        return {
            "response": response,
            "inj_score": inj_score,
            "drift_score": drift_score,
            "blocked": True,
            "reason": reason,
        }

    save_checkpoint(agent, original_prompt, out, inj_score, drift_score)

    log_event({
        "agent": agent,
        "prompt": original_prompt,
        "inj_score": inj_score,
        "drift_score": drift_score,
        "blocked": False,
        "reason": None,
        "output": out,
    })

    return {
        "response": out,
        "inj_score": inj_score,
        "drift_score": drift_score,
        "blocked": False,
        "reason": None,
    }
