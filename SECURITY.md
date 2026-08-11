# Security Policy

## Reporting a vulnerability

Do **not** open a public issue for a suspected vulnerability or safety-boundary failure in `drift_orchestrator`.

Preferred reporting path:

1. Use **Security → Report a vulnerability** for this repository when GitHub private vulnerability reporting is available.
2. If that flow is unavailable, email **badbanana@proton.me** with the subject `drift_orchestrator security report`.

Include the affected commit/version, file or execution path, expected invariant, observed behavior, minimal reproduction steps, impact, and any proposed mitigation. Do not send unrelated credentials, private data, or third-party material you are not authorized to disclose.

## Security-relevant boundaries

### Import verification

Historical versions of `verifier/python_imports.py` used `importlib.import_module()` on names extracted from analyzed text. The current verifier uses allowlist classification instead of importing analyzed module names.

### CLI flag verification

`verify_cli_flags()` accepts an optional `command` parameter that can execute `[command, "--help"]`. Pipeline calls keep this path disabled by default. Never populate the executable name from untrusted input.

### Public gateway adapter

`gateway_adapter.py` is intended for local experiment reruns. It binds to `127.0.0.1` by default and forwards prompts to the configured Ollama endpoint. Exposing the adapter on a non-loopback interface changes the threat model and should be treated as an explicit operator decision.

### Live signal API

`live_signal_api.py` exposes unauthenticated session, snapshot, SSE, registration, and score-update endpoints for the local research dashboard. Its development entrypoint binds to `127.0.0.1` by default. Setting `DRIFT_SIGNAL_HOST` to a non-loopback address exposes a control surface that can alter telemetry state and therefore changes the threat model; do not expose it to untrusted networks without adding an appropriate authentication/authorization layer.

### External model APIs

Modes that use external model providers can send message content to those providers and read credentials from environment variables. Never commit API keys or assume locally handled research data remains local when an external-provider mode is enabled.

## Supported state

Security findings should be reported against the current default branch or a specifically identified historical release/commit. Older experimental revisions may intentionally retain superseded behavior for provenance; a historical finding should therefore name the exact revision rather than assuming it remains present in current code.

## Disclosure

Please allow a reasonable remediation and verification window before public disclosure. Confirmed fixes should be documented when practical, and reporter credit is welcome unless anonymity is requested.
