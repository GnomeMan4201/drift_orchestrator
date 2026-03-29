import re
import sys

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
    "unittest", "doctest", "pdb", "gc", "weakref", "numbers",
    "decimal", "fractions", "statistics", "random", "secrets",
    "zipfile", "tarfile", "gzip", "bz2", "lzma", "zlib",
    "xml", "html", "email", "smtplib", "getpass", "configparser",
])

KNOWN_THIRD_PARTY = set([
    "requests", "flask", "django", "fastapi", "sqlalchemy", "pydantic",
    "numpy", "pandas", "scipy", "matplotlib", "sklearn", "torch",
    "tensorflow", "pytest", "click", "rich", "typer", "httpx",
    "aiohttp", "celery", "redis", "boto3", "paramiko", "cryptography",
    "jwt", "yaml", "toml", "PIL", "cv2", "bs4", "lxml", "scrapy",
    "selenium", "playwright", "sentence_transformers", "transformers",
    "huggingface_hub", "tokenizers", "safetensors",
])

INVENTED_PYTHON_APIS = [
    (r'requests\.get\s*\(.*verify_fingerprint', "requests.get(verify_fingerprint=...) is not a real parameter"),
    (r'os\.path\.validate\s*\(', "os.path.validate() does not exist"),
    (r'json\.validate\s*\(', "json.validate() does not exist — use jsonschema"),
    (r'importlib\.verify\s*\(', "importlib.verify() does not exist"),
    (r'sys\.validate\s*\(', "sys.validate() does not exist"),
    (r'logging\.configure\s*\(', "logging.configure() does not exist — use logging.basicConfig()"),
    (r'logging\.transmit\s*\(', "logging.transmit() does not exist"),
    (r'argparse\.validate\s*\(', "argparse.validate() does not exist"),
    (r'dict\.merge\s*\(', "dict.merge() does not exist — use dict.update() or | operator"),
    (r'list\.find\s*\(', "list.find() does not exist — use list.index()"),
    (r'list\.search\s*\(', "list.search() does not exist"),
    (r'str\.contains\s*\(', "str.contains() does not exist — use 'in' operator"),
    (r'asyncio\.run_forever\s*\(', "asyncio.run_forever() does not exist — use loop.run_forever()"),
    (r'from\s+std\.', "std.* is not a Python module (Rust stdlib syntax)"),
    (r'from\s+node\.', "node.* is not a Python module (Node.js syntax)"),
    (r'\.auto_flush\s*\(', ".auto_flush() is not a standard method"),
    (r'\.auto_retry\s*\(', ".auto_retry() is not a standard method"),
    (r'\.remote_validate\s*\(', ".remote_validate() is not a standard method"),
    (r'errorlib', "errorlib is not a real Python module"),
    (r'retrylib', "retrylib is not a real Python module"),
    (r'magiclib', "magiclib is not a real Python module"),
]

INVENTED_CLI_FLAGS = [
    "--ultra-scan", "--ghost-mode", "--turbo", "--ai-mode",
    "--bypass-auth", "--skip-verify", "--disable-security",
    "--no-check", "--force-root", "--override-policy",
]


def _get_stdlib_names():
    if hasattr(sys, "stdlib_module_names"):
        return sys.stdlib_module_names
    return KNOWN_STDLIB


def _classify_module(mod):
    stdlib = _get_stdlib_names()
    if mod in stdlib or mod in KNOWN_STDLIB:
        return "stdlib"
    if mod in KNOWN_THIRD_PARTY:
        return "known_third_party"
    return "unknown"


def _extract_code_imports(text):
    found = []
    for line in text.splitlines():
        line = line.strip()
        m1 = re.match(r'^import\s+([\w\.]+)', line)
        m2 = re.match(r'^from\s+([\w\.]+)\s+import', line)
        if m1:
            found.append(m1.group(1).split(".")[0])
        elif m2:
            found.append(m2.group(1).split(".")[0])
    return list(set(found))


def detect_hallucinations(text):
    findings = []

    code_imports = _extract_code_imports(text)
    for mod in code_imports:
        classification = _classify_module(mod)
        if classification == "unknown":
            findings.append({
                "type": "invented_import",
                "severity": "HIGH",
                "detail": f"module '{mod}' not in stdlib or known third-party list — likely invented"
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
