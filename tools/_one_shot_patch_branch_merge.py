from pathlib import Path

path = Path("branch_merge.py")
text = path.read_text(encoding="utf-8")

replacements = [
    (
        "from session_manager import create_branch, create_session\n",
        "from session_manager import create_session\n",
        "unused create_branch import",
    ),
    (
        '    print(f"\\n  SESSION RANKING")\n',
        '    print("\\n  SESSION RANKING")\n',
        "placeholder-free ranking f-string",
    ),
    (
        '\n\ndef fetch_one(table, where_clause="", params=None):\n'
        '    from sqlite_store import fetch_one as _fetch_one\n'
        '    return _fetch_one(table, where_clause, params)',
        "",
        "redundant fetch_one wrapper",
    ),
]

for old, new, label in replacements:
    matches = text.count(old)
    if matches != 1:
        raise SystemExit(f"unexpected source shape for {label}: {matches} matches")
    text = text.replace(old, new, 1)

path.write_text(text.rstrip() + "\n", encoding="utf-8")
