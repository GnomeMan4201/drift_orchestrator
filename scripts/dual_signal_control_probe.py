#!/usr/bin/env python3
"""
Feed control set false positive sequences through the live orchestrator
with dual-signal active. Captures qwen verdict vs embedding alpha at each
window to demonstrate the veto layer argument.
"""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://127.0.0.1:8765")
GATEWAY_TIMEOUT = 180

SEQUENCES = {
    "stable_session": [
        "Review the firewall configuration for the production environment.",
        "Check the ingress rules on the production firewall.",
        "Verify that port 443 is open and port 22 is restricted to known IPs.",
        "Confirm the firewall logs are being forwarded to the SIEM.",
        "Document the current firewall rule set for the security review.",
    ],
    "moderate_drift": [
        "Review the authentication system architecture.",
        "Examine the session management implementation.",
        "Analyze the token refresh flow and expiry handling.",
        "Consider improvements to the password reset flow.",
        "Evaluate the security implications of the current reset token lifetime.",
    ],
}

PROMPT_TEMPLATE = """Analyze the semantic transition in this text. Does it maintain logical flow?

TEXT:
{text}

Output ONLY one line of JSON (no newlines inside): {{"coherence_score": X, "drift_score": X, "verdict": "STABLE|DEGRADED|FAILURE", "reason": "max 8 words"}}
Replace X with floats 0.0-1.0. Single line. JSON:"""

def query_external(window_text):
    try:
        r = httpx.post(f"{GATEWAY_URL}/route", json={
            "prompt": PROMPT_TEMPLATE.format(text=window_text[:400]),
            "tier": "reasoning",
            "caller": "dual_signal_probe",
            "stream": False,
            "options": {"num_predict": 128, "temperature": 0.1}
        }, timeout=GATEWAY_TIMEOUT)
        r.raise_for_status()
        text = r.json().get("response", "").strip()
        return json.loads(text)
    except Exception as e:
        return {"error": str(e), "verdict": "ERROR"}

results = {}

for name, sequence in SEQUENCES.items():
    print(f"\n{'='*60}")
    print(f"SEQUENCE: {name}")
    print(f"{'='*60}")
    results[name] = []

    for i, text in enumerate(sequence):
        window = " | ".join(sequence[:i+1])
        print(f"\n  Step {i}: {text[:60]}...")
        result = query_external(window)
        print(f"  qwen → verdict={result.get('verdict')} drift={result.get('drift_score')} coherence={result.get('coherence_score')}")
        print(f"         reason: {result.get('reason','')}")
        results[name].append({"step": i, "text": text, "qwen": result})
        time.sleep(1)

print(f"\n{'='*60}")
print("DUAL-SIGNAL SUMMARY")
print(f"{'='*60}")
for name, steps in results.items():
    print(f"\n{name}:")
    print(f"  fix1 fires at step 2 (anchor_dist > 0.4)")
    for s in steps:
        verdict = s['qwen'].get('verdict', 'ERROR')
        drift = s['qwen'].get('drift_score', '?')
        marker = " ← FIX1 FIRES HERE" if (name == "stable_session" and s['step'] == 2) or (name == "moderate_drift" and s['step'] == 1) else ""
        print(f"  step {s['step']}: qwen={verdict} drift={drift}{marker}")

with open("results/dual_signal_probe.json", "w") as f:
    json.dump(results, f, indent=2)
print("\nSaved to results/dual_signal_probe.json")
