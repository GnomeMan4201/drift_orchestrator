# Security Policy

## Reporting a Vulnerability

To report a security vulnerability in drift_orchestrator, open a GitHub issue
marked **[SECURITY]** or contact the maintainer directly via GitHub.

Please include:
- Description of the vulnerability
- Steps to reproduce
- Affected versions
- Potential impact

## Known Security Considerations

### Import Verification (verifier/python_imports.py)

Prior to the security hardening patch, the import verifier called
`importlib.import_module()` on module names extracted from analyzed text.
This has been replaced with a pure allowlist classification approach.
Module names found in analyzed text are now classified against a known
stdlib and third-party allowlist without executing any imports.

### CLI Flag Verification (verifier/cli_flags.py)

`verify_cli_flags()` accepts an optional `command` parameter that, if
provided, will run `subprocess.run([command, "--help"])`. This is disabled
by default in all pipeline calls. Do not pass untrusted input as `command`.

### API Keys

Agent and backend modes read API keys from environment variables
(`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`). Never hardcode credentials.
Full message histories are sent to external LLM APIs when using these modes.

## Supported Versions

| Version | Supported |
|---------|-----------|
| v0.11.0+ | ✓ |
| < v0.11.0 | security hardening not applied |
