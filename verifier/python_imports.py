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
    "unittest", "doctest", "pdb", "profile", "cProfile", "timeit",
    "xml", "html", "email", "smtplib", "ftplib", "telnetlib",
    "zipfile", "tarfile", "gzip", "bz2", "lzma", "zlib",
    "decimal", "fractions", "statistics", "random", "secrets",
    "getpass", "getopt", "readline", "rlcompleter", "code",
    "dis", "token", "tokenize", "keyword", "builtins",
    "gc", "weakref", "abc", "numbers", "cmath",
    "pwd", "grp", "termios", "tty", "pty", "fcntl", "pipes",
    "resource", "syslog", "optparse", "configparser",
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


def _get_stdlib_names():
    if hasattr(sys, "stdlib_module_names"):
        return sys.stdlib_module_names
    return KNOWN_STDLIB


def extract_imports_from_text(text):
    imports = []
    for line in text.splitlines():
        line = line.strip()
        m1 = re.match(r'^import\s+([\w\.]+)', line)
        m2 = re.match(r'^from\s+([\w\.]+)\s+import\s+', line)
        if m1:
            imports.append(m1.group(1).split(".")[0])
        elif m2:
            imports.append(m2.group(1).split(".")[0])
    return list(set(imports))


def classify_module(mod):
    stdlib = _get_stdlib_names()
    if mod in stdlib or mod in KNOWN_STDLIB:
        return "stdlib"
    if mod in KNOWN_THIRD_PARTY:
        return "known_third_party"
    return "unknown"


def verify_imports(text):
    imports = extract_imports_from_text(text)
    results = {}
    failed = 0

    for mod in imports:
        classification = classify_module(mod)
        if classification == "stdlib":
            results[mod] = {"status": "ok", "classification": "stdlib", "error": None}
        elif classification == "known_third_party":
            results[mod] = {"status": "ok", "classification": "third_party", "error": None}
        else:
            results[mod] = {
                "status": "missing",
                "classification": "unknown",
                "error": f"module '{mod}' not in stdlib or known third-party list"
            }
            failed += 1

    risk = failed / len(imports) if imports else 0.0

    return {
        "imports": results,
        "risk_score": round(risk, 4),
        "total": len(imports),
        "failed": failed
    }
