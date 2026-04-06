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
from firewall.sensation import collect_state, derive_posture, inject_context

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

    state = collect_state()
    posture = derive_posture(state)
    effective_drift = max(float(drift_score or 0.0), float(state.anomaly_level or 0.0) * 0.25)

    if prompt.startswith("[BLOCKED"):
        last_good = get_last_good_response(agent) if use_rollback else None
        response = last_good or prompt
        reason = "sanitizer_block_with_rollback" if last_good else "sanitizer_block"

        log_event({
            "agent": agent,
            "prompt": original_prompt,
            "inj_score": inj_score,
            "drift_score": effective_drift,
            "blocked": True,
            "reason": reason,
            "output": response,
            "posture": posture.to_dict(),
            "state_vector": state.to_dict(),
        })

        return {
            "response": response,
            "inj_score": inj_score,
            "drift_score": effective_drift,
            "blocked": True,
            "reason": reason,
        }

    if posture.name == "LOCKDOWN":
        last_good = get_last_good_response(agent) if use_rollback else None
        response = last_good or "[LOCKDOWN BLOCK]"
        reason = "lockdown_policy"

        log_event({
            "agent": agent,
            "prompt": original_prompt,
            "inj_score": inj_score,
            "drift_score": effective_drift,
            "blocked": True,
            "reason": reason,
            "output": response,
            "posture": posture.to_dict(),
            "state_vector": state.to_dict(),
        })

        return {
            "response": response,
            "inj_score": inj_score,
            "drift_score": effective_drift,
            "blocked": True,
            "reason": reason,
        }

    if not expected_exact:
        prompt = inject_context(prompt, posture, state)

    decision = score_request(prompt, drift_score=effective_drift)
    if decision["blocked"] or effective_drift > posture.max_drift:
        last_good = get_last_good_response(agent) if use_rollback else None
        response = last_good or "[BLOCKED: control-plane anomaly detected]"
        if effective_drift > posture.max_drift:
            reason = "posture_drift_rollback" if last_good else "posture_drift"
        else:
            reason = f'{decision["reason"]}_rollback' if last_good else decision["reason"]

        log_event({
            "agent": agent,
            "prompt": original_prompt,
            "inj_score": float(decision["inj_score"]),
            "drift_score": effective_drift,
            "blocked": True,
            "reason": reason,
            "output": response,
            "posture": posture.to_dict(),
            "state_vector": state.to_dict(),
        })

        return {
            "response": response,
            "inj_score": float(decision["inj_score"]),
            "drift_score": effective_drift,
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
            "drift_score": effective_drift,
            "blocked": True,
            "reason": reason,
            "output": response,
            "posture": posture.to_dict(),
            "state_vector": state.to_dict(),
        })

        return {
            "response": response,
            "inj_score": inj_score,
            "drift_score": effective_drift,
            "blocked": True,
            "reason": reason,
        }

    save_checkpoint(agent, original_prompt, out, inj_score, effective_drift)

    log_event({
        "agent": agent,
        "prompt": original_prompt,
        "inj_score": inj_score,
        "drift_score": effective_drift,
        "blocked": False,
        "reason": None,
        "output": out,
        "posture": posture.to_dict(),
        "state_vector": state.to_dict(),
    })

    return {
        "response": out,
        "inj_score": inj_score,
        "drift_score": effective_drift,
        "blocked": False,
        "reason": None,
    }
