import re
import ast


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


def extract_code_blocks(text):
    fenced = re.findall(r'```(?:python)?\s*(.*?)```', text, re.DOTALL)
    if fenced:
        return fenced
    if looks_like_python(text):
        inline_defs = re.findall(r'((?:(?:def |class |async def )\w.*(?:\n|$))+)', text)
        return inline_defs
    return []


def extract_function_signatures(text):
    blocks = extract_code_blocks(text)
    if not blocks:
        return [], None
    sigs = []
    for block in blocks:
        try:
            tree = ast.parse(block)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = [arg.arg for arg in node.args.args]
                sigs.append({
                    "name": node.name,
                    "args": args,
                    "num_args": len(args),
                    "has_varargs": node.args.vararg is not None,
                    "has_kwargs": node.args.kwarg is not None,
                    "lineno": node.lineno,
                    "is_async": isinstance(node, ast.AsyncFunctionDef),
                    "decorators": [ast.unparse(d) if hasattr(ast, 'unparse') else "" for d in node.decorator_list]
                })
    return sigs, None


def verify_signatures(text):
    if not looks_like_python(text):
        return {"signatures": [], "issues": [], "risk_score": 0.0, "parse_error": None}
    sigs, parse_error = extract_function_signatures(text)
    issues = []
    for sig in sigs:
        if sig["num_args"] > 10:
            issues.append({
                "type": "too_many_args",
                "function": sig["name"],
                "detail": f"{sig['num_args']} args at line {sig['lineno']}"
            })
        if sig["name"].startswith("__") and not sig["name"].endswith("__"):
            issues.append({
                "type": "dunder_mismatch",
                "function": sig["name"],
                "detail": f"starts with __ but does not end with __ at line {sig['lineno']}"
            })
    risk = len(issues) / max(1, len(sigs)) if sigs else 0.0
    return {"signatures": sigs, "issues": issues, "risk_score": round(min(1.0, risk), 4), "parse_error": None}
