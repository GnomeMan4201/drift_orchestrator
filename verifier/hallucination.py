import re
import importlib

KNOWN_STDLIB = set([
    "os", "sys", "re", "json", "csv", "math", "time", "datetime", "uuid",
    "hashlib", "logging", "argparse", "ast", "inspect", "importlib",
    "subprocess", "pathlib", "shutil", "glob", "io", "functools",
    "itertools", "collections", "typing", "dataclasses", "abc",
    "threading", "asyncio", "socket", "http", "urllib", "base64",
    "struct", "copy", "pprint", "traceback", "warnings", "contextlib",
    "sqlite3", "pickle", "shelve", "tempfile", "enum", "string",
    "textwrap", "difflib", "heapq", "bisect", "array", "queue",
    "multiprocessing", "concurrent", "signal", "platform", "ctypes",
])

KNOWN_THIRD_PARTY = set([
    "requests", "flask", "django", "fastapi", "sqlalchemy", "pydantic",
    "numpy", "pandas", "scipy", "matplotlib", "sklearn", "torch", "tensorflow",
    "pytest", "click", "rich", "typer", "httpx", "aiohttp", "celery",
    "redis", "boto3", "paramiko", "cryptography", "jwt", "yaml", "toml",
    "PIL", "cv2", "bs4", "lxml", "scrapy", "selenium", "playwright",
])

INVENTED_PYTHON_APIS = [
    (r'requests\.get\s*\(.*verify_fingerprint', "requests.get(verify_fingerprint=...) is not a real parameter"),
    (r'os\.path\.validate\s*\(', "os.path.validate() does not exist"),
    (r'json\.validate\s*\(', "json.validate() does not exist — use jsonschema"),
    (r'importlib\.verify\s*\(', "importlib.verify() does not exist"),
    (r'sys\.validate\s*\(', "sys.validate() does not exist"),
    (r'logging\.configure\s*\(', "logging.configure() does not exist — use logging.basicConfig()"),
    (r'argparse\.validate\s*\(', "argparse.validate() does not exist"),
    (r'dict\.merge\s*\(', "dict.merge() does not exist — use dict.update() or | operator"),
    (r'list\.find\s*\(', "list.find() does not exist — use list.index()"),
    (r'str\.contains\s*\(', "str.contains() does not exist — use 'in' operator"),
    (r'asyncio\.run_forever\s*\(', "asyncio.run_forever() does not exist — use loop.run_forever()"),
    (r'from\s+std\.', "std.* is not a Python module (Rust stdlib syntax)"),
    (r'from\s+node\.', "node.* is not a Python module (Node.js syntax)"),
]

INVENTED_CLI_FLAGS = [
    "--ultra-scan", "--ghost-mode", "--turbo", "--ai-mode",
    "--bypass-auth", "--skip-verify", "--disable-security",
    "--no-check", "--force-root", "--override-policy",
]

PROSE_IMPORT_NOISE = set([
    "the", "a", "an", "it", "is", "paths", "calls", "validation",
    "this", "that", "we", "you", "Display", "choices", "results",
    "use", "run", "set", "get", "put", "let", "can", "will", "should",
])


def _check_import(mod):
    if mod in KNOWN_STDLIB or mod in KNOWN_THIRD_PARTY:
        return "known"
    try:
        importlib.import_module(mod)
        return "ok"
    except ImportError:
        return "missing"
    except Exception:
        return "error"


def _extract_code_imports(text):
    found = []
    for line in text.splitlines():
        line = line.strip()
        m1 = re.match(r'^import\s+([\w\.]+)', line)
        m2 = re.match(r'^from\s+([\w\.]+)\s+import', line)
        if m1:
            found.append(m1.group(1))
        elif m2:
            found.append(m2.group(1))
    return found


def detect_hallucinations(text):
    findings = []

    code_imports = _extract_code_imports(text)
    for mod in code_imports:
        if mod in KNOWN_STDLIB or mod in KNOWN_THIRD_PARTY:
            continue
        status = _check_import(mod)
        if status == "missing":
            findings.append({
                "type": "invented_import",
                "severity": "HIGH",
                "detail": f"module '{mod}' cannot be imported — likely invented"
            })

    for pattern, explanation in INVENTED_PYTHON_APIS:
        if re.search(pattern, text):
            findings.append({
                "type": "invented_api",
                "severity": "HIGH",
                "detail": explanation
            })

    for flag in INVENTED_CLI_FLAGS:
        if flag in text:
            findings.append({
                "type": "invented_cli_flag",
                "severity": "HIGH",
                "detail": f"flag '{flag}' does not exist in any standard tool"
            })

    high = sum(1 for f in findings if f["severity"] == "HIGH")
    med = sum(1 for f in findings if f["severity"] == "MEDIUM")
    risk = min(1.0, high * 0.4 + med * 0.2)

    return {"findings": findings, "risk_score": round(risk, 4), "count": len(findings)}
