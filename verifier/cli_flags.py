import subprocess
import re

_help_cache = {}

KNOWN_FAKE_FLAGS = {
    "--ultra-scan", "--ghost-mode", "--turbo", "--ai-mode",
    "--bypass-auth", "--skip-verify", "--disable-security",
    "--no-check", "--force-root", "--override-policy",
}

KNOWN_REAL_FLAGS = {
    "--help", "--version", "--verbose", "--quiet", "--output",
    "--config", "--format", "--debug", "--log", "--file",
    "--input", "--dry-run", "--force", "--all", "--list",
    "--host", "--port", "--timeout", "--retry", "--max-retries",
}


def looks_like_cli(text):
    return bool(re.search(r'(?:^|\s)(--[\w\-]+|-[a-zA-Z])\b', text))


def _get_help_output(command):
    if command in _help_cache:
        return _help_cache[command]
    try:
        result = subprocess.run([command, "--help"], capture_output=True, text=True, timeout=5)
        output = result.stdout + result.stderr
    except Exception:
        output = ""
    _help_cache[command] = output
    return output


def extract_flags_from_text(text):
    flags = re.findall(r'(?:^|\s)(--[\w\-]+|-[a-zA-Z])\b', text)
    return list(set(flags))


def verify_cli_flags(text, command=None):
    if not looks_like_cli(text):
        return {"flags": [], "results": {}, "risk_score": 0.0, "suspicious": [], "command": command}
    flags = extract_flags_from_text(text)
    if not flags:
        return {"flags": [], "results": {}, "risk_score": 0.0, "suspicious": [], "command": command}

    help_text = _get_help_output(command) if command else ""
    results = {}
    suspicious = []

    for flag in flags:
        if flag in KNOWN_FAKE_FLAGS:
            results[flag] = {"status": "invented", "in_help": False}
            suspicious.append(flag)
        elif flag in KNOWN_REAL_FLAGS:
            results[flag] = {"status": "ok", "in_help": True}
        elif help_text:
            found = flag in help_text
            results[flag] = {"status": "ok" if found else "unknown", "in_help": found}
            if not found:
                suspicious.append(flag)
        else:
            results[flag] = {"status": "unverified", "in_help": None}

    invented = sum(1 for v in results.values() if v["status"] == "invented")
    unknown = sum(1 for v in results.values() if v["status"] == "unknown")
    risk = min(1.0, (invented * 0.6 + unknown * 0.1) / max(1, len(flags)))

    return {"flags": flags, "results": results, "risk_score": round(risk, 4), "suspicious": suspicious, "command": command}
