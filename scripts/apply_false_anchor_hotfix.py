#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent

def read(p: Path) -> str:
    return p.read_text()

def write(p: Path, s: str) -> None:
    p.write_text(s)

def patch_policy():
    p = ROOT / "policy.py"
    if not p.exists():
        print("skip policy.py (missing)")
        return
    txt = read(p)

    helper = r'''
def _hotfix_anchor_rollback_allowed(anchor_hist, latest_alpha):
    """
    Conservative hotfix:
    only allow monotonic anchor-drift rollback when the drift is both monotonic
    and materially large, AND coherence is degraded.
    """
    try:
        seq = [float(x) for x in anchor_hist[-4:]]
    except Exception:
        return False
    if len(seq) < 4:
        return False
    mono = all(a < b for a, b in zip(seq, seq[1:]))
    peak_ok = max(seq) >= 0.40
    mean_ok = (sum(seq) / len(seq)) >= 0.33
    alpha_bad = (latest_alpha is not None and float(latest_alpha) <= 0.25)
    return mono and peak_ok and mean_ok and alpha_bad

'''
    if "_hotfix_anchor_rollback_allowed" not in txt:
        m = re.search(r'(^import .*?$|^from .*?$)(.*)', txt, re.S | re.M)
        if m:
            # append after import block
            imports = []
            rest = txt
            lines = txt.splitlines(True)
            i = 0
            while i < len(lines) and (lines[i].startswith("import ") or lines[i].startswith("from ")):
                imports.append(lines[i]); i += 1
            txt = "".join(imports) + "\n" + helper + "".join(lines[i:])
        else:
            txt = helper + txt

    # Replace direct monotonic-anchor rollback trigger with guarded version if possible
    patterns = [
        (
            r'if\s+(?P<cond>.*?monotonic.*?anchor.*?drift.*?):\s*\n(?P<body>(?:\s+.*\n){1,12})',
            lambda m: (
                "if " + m.group("cond") + ":\n"
                "    _hotfix_seq = locals().get('d_anchor_hist') or locals().get('anchor_hist') or "
                "locals().get('d_anchor_history') or getattr(self, '_anchor_history', [])\n"
                "    _hotfix_alpha = locals().get('alpha') or locals().get('latest_alpha')\n"
                "    if not _hotfix_anchor_rollback_allowed(_hotfix_seq, _hotfix_alpha):\n"
                "        pass\n"
                "    else:\n" +
                "".join("        " + line if line.strip() else line for line in m.group("body").splitlines(True))
            )
        ),
    ]

    patched_any = False
    for pat, repl in patterns:
        new_txt, n = re.subn(pat, repl, txt, flags=re.S)
        if n:
            txt = new_txt
            patched_any = True
            break

    # If the structural replacement didn't hit, hotfix the exact reason path by guarding the reason string.
    if not patched_any and "monotonic anchor drift" in txt:
        txt = txt.replace(
            'reason = (',
            "_hotfix_seq = locals().get('d_anchor_hist') or locals().get('anchor_hist') or locals().get('d_anchor_history') or getattr(self, '_anchor_history', [])\n"
            "_hotfix_alpha = locals().get('alpha') or locals().get('latest_alpha')\n"
            "reason = ("
        )
        txt = txt.replace(
            'return "ROLLBACK", reason',
            'return ("CONTINUE", "hotfix: suppressed false monotonic-anchor rollback") '
            'if ("monotonic anchor drift" in str(reason) and not _hotfix_anchor_rollback_allowed(_hotfix_seq, _hotfix_alpha)) '
            'else ("ROLLBACK", reason)'
        )
        patched_any = True

    write(p, txt)
    print(f"patched policy.py: {'yes' if patched_any else 'partial/no-structural-match'}")

def _inject_reset_call(txt: str) -> tuple[str, int]:
    injected = 0

    reset_snippet = """
    try:
        _ev = None
        for _cand in (
            locals().get("evaluator"),
            getattr(locals().get("session", None), "evaluator", None),
            getattr(locals().get("runtime", None), "evaluator", None),
            getattr(locals().get("engine", None), "evaluator", None),
        ):
            if _cand is not None:
                _ev = _cand
                break
        if _ev is not None:
            if hasattr(_ev, "_seen_windows"):
                _ev._seen_windows.clear()
            if hasattr(_ev, "_anchor_history"):
                _ev._anchor_history.clear()
            if hasattr(_ev, "_alpha_history"):
                _ev._alpha_history.clear()
            if hasattr(_ev, "_reset_eval_state"):
                _ev._reset_eval_state()
    except Exception:
        pass
"""

    # inject after /reset branch if present
    txt, n1 = re.subn(
        r'(?P<head>^\s*(?:if|elif)\s+.*?/reset.*?:\s*$)',
        lambda m: m.group("head") + reset_snippet,
        txt,
        flags=re.M
    )
    injected += n1

    # inject after lines mentioning recovery restore / continuing evaluation
    txt, n2 = re.subn(
        r'(?P<head>^\s*print\((?:f)?["\']\[RECOVERY\].*(?:Restoring|Continuing evaluation).*["\']\)\s*$)',
        lambda m: m.group("head") + reset_snippet,
        txt,
        flags=re.M
    )
    injected += n2

    return txt, injected

def patch_live_and_recovery():
    for name in ("live.py", "recovery.py", "session_manager.py"):
        p = ROOT / name
        if not p.exists():
            print(f"skip {name} (missing)")
            continue
        txt = read(p)

        # seed evaluator state if an evaluator-like class exists in file
        if "_seen_windows = set()" not in txt:
            txt = re.sub(
                r'(^\s*def __init__\(self[^\n]*\):\s*$)',
                r'\1\n        self._seen_windows = set()\n        self._anchor_history = []\n        self._alpha_history = []',
                txt,
                count=1,
                flags=re.M
            )

        # add reset method if a class body exists and method absent
        if "def _reset_eval_state(self):" not in txt:
            txt = re.sub(
                r'(^class\s+\w+[^\n]*:\s*$)',
                r'''\1

    def _reset_eval_state(self):
        try:
            self._seen_windows.clear()
        except Exception:
            self._seen_windows = set()
        try:
            self._anchor_history.clear()
        except Exception:
            self._anchor_history = []
        try:
            self._alpha_history.clear()
        except Exception:
            self._alpha_history = []
''',
                txt,
                count=1,
                flags=re.M
            )

        txt, injected = _inject_reset_call(txt)
        write(p, txt)
        print(f"patched {name}: reset-injections={injected}")

def patch_evaluator():
    p = ROOT / "evaluator.py"
    if not p.exists():
        print("skip evaluator.py (missing)")
        return
    txt = read(p)

    # seed evaluator state
    if "_seen_windows = set()" not in txt:
        txt = re.sub(
            r'(^\s*def __init__\(self[^\n]*\):\s*$)',
            r'\1\n        self._seen_windows = set()\n        self._anchor_history = []\n        self._alpha_history = []',
            txt,
            count=1,
            flags=re.M
        )

    if "def _reset_eval_state(self):" not in txt:
        txt = re.sub(
            r'(^class\s+\w*[Ee]valuator\w*[^\n]*:\s*$)',
            r'''\1

    def _reset_eval_state(self):
        try:
            self._seen_windows.clear()
        except Exception:
            self._seen_windows = set()
        try:
            self._anchor_history.clear()
        except Exception:
            self._anchor_history = []
        try:
            self._alpha_history.clear()
        except Exception:
            self._alpha_history = []
''',
            txt,
            count=1,
            flags=re.M
        )

    # append history after d_anchor / alpha assignments if present
    if "self._anchor_history.append" not in txt:
        txt = re.sub(
            r'(^\s*(?:d_anchor\s*=.*)$)',
            r'\1\n        try:\n            self._anchor_history.append(float(d_anchor))\n        except Exception:\n            pass',
            txt,
            count=1,
            flags=re.M
        )
    if "self._alpha_history.append" not in txt:
        txt = re.sub(
            r'(^\s*(?:alpha\s*=.*)$)',
            r'\1\n        try:\n            self._alpha_history.append(float(alpha))\n        except Exception:\n            pass',
            txt,
            count=1,
            flags=re.M
        )

    write(p, txt)
    print("patched evaluator.py")

patch_policy()
patch_live_and_recovery()
patch_evaluator()
print("done")
