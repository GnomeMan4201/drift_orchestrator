import importlib
import re

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


def looks_like_python(text):
    markers = [
        "import " in text,
        "def " in text,
        "class " in text,
        "return " in text,
        "lambda " in text,
        bool(re.search(r'\w+\(.*\).*:', text)),
    ]
    return sum(markers) >= 2


def extract_imports_from_text(text):
    imports = []
    for line in text.splitlines():
        line = line.strip()
        m1 = re.match(r'^import\s+([\w\.]+)', line)
        m2 = re.match(r'^from\s+([\w\.]+)\s+import\s+', line)
        if m1:
            imports.append(m1.group(1))
        elif m2:
            imports.append(m2.group(1))
    return list(set(imports))


def verify_imports(text):
    if not looks_like_python(text):
        return {"imports": {}, "risk_score": 0.0, "total": 0, "failed": 0}
    imports = extract_imports_from_text(text)
    results = {}
    for mod in imports:
        if mod in KNOWN_STDLIB:
            results[mod] = {"status": "ok", "error": None}
            continue
        try:
            importlib.import_module(mod)
            results[mod] = {"status": "ok", "error": None}
        except ImportError as e:
            results[mod] = {"status": "missing", "error": str(e)}
        except Exception as e:
            results[mod] = {"status": "error", "error": str(e)}
    failed = sum(1 for v in results.values() if v["status"] != "ok")
    risk = failed / len(imports) if imports else 0.0
    return {"imports": results, "risk_score": round(risk, 4), "total": len(imports), "failed": failed}
