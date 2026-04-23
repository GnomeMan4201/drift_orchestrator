#!/usr/bin/env python3
"""
deploy.py
==========
Single command to push everything to the right places.

Usage:
  python deploy.py             -- deploy all
  python deploy.py --paper     -- dev.to paper only
  python deploy.py --github    -- git push only
  python deploy.py --check     -- verify all endpoints live
"""
import sys, os, subprocess, urllib.request, urllib.error, json
from pathlib import Path
from datetime import datetime

REPO     = Path(__file__).parent
PAPER    = REPO / "papers" / "second_order_injection.md"
DEVTO_ID = 3538640
API_KEY  = Path.home() / ".devto_api_key"
HEADERS  = {
    "Content-Type": "application/json",
    "Accept": "application/vnd.forem.api-v1+json",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
}

URLS = {
    "research_portal":  "https://gnomeman4201.github.io/drift_orchestrator/",
    "governor_demo":    "https://gnomeman4201.github.io/drift_orchestrator/governor.html",
    "devto_paper":      "https://dev.to/gnomeman4201/second-order-injection-attacking-the-evaluator-in-llm-safety-monitors-1jnh",
    "github_repo":      "https://github.com/GnomeMan4201/drift_orchestrator",
}

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def ok(msg):  print(f"  {GREEN}✓{RESET} {msg}")
def err(msg): print(f"  {RED}✗{RESET} {msg}")
def info(msg):print(f"  {BLUE}→{RESET} {msg}")
def warn(msg):print(f"  {YELLOW}!{RESET} {msg}")
def head(msg):print(f"\n{BOLD}{msg}{RESET}")

def devto_update():
    head("dev.to — Updating paper")
    if not API_KEY.exists():
        err("~/.devto_api_key not found")
        return False
    if not PAPER.exists():
        err(f"Paper not found: {PAPER}")
        return False

    key  = API_KEY.read_text().strip()
    body = PAPER.read_text()
    info(f"Paper: {len(body)} bytes, {len(body.splitlines())} lines")

    data = json.dumps({"article": {"body_markdown": body}}).encode()
    req  = urllib.request.Request(
        f"https://dev.to/api/articles/{DEVTO_ID}",
        data=data,
        headers={**HEADERS, "api-key": key},
        method="PUT"
    )
    try:
        with urllib.request.urlopen(req) as r:
            result = json.loads(r.read())
            ok(f"Updated: {result.get('url')}")
            return True
    except urllib.error.HTTPError as e:
        err(f"HTTP {e.code}: {e.read().decode()[:200]}")
        return False

def git_push(msg=None):
    head("GitHub — Pushing")
    os.chdir(REPO)

    # Stage all tracked changes
    result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    if not result.stdout.strip():
        warn("Nothing to commit — working tree clean")
        return True

    info(f"Changes:\n{result.stdout.rstrip()}")

    # Add all
    subprocess.run(["git", "add", "-A"], check=True)

    # Commit
    commit_msg = msg or f"deploy: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    result = subprocess.run(["git", "commit", "-m", commit_msg], capture_output=True, text=True)
    if result.returncode != 0:
        if "nothing to commit" in result.stdout:
            warn("Nothing to commit")
            return True
        err(f"Commit failed: {result.stderr}")
        return False

    info(f"Committed: {commit_msg}")

    # Push
    result = subprocess.run(["git", "push"], capture_output=True, text=True)
    if result.returncode != 0:
        err(f"Push failed: {result.stderr}")
        return False

    ok("Pushed to github.com:GnomeMan4201/drift_orchestrator.git")
    return True

def check_live():
    head("Checking all endpoints")
    all_ok = True
    for name, url in URLS.items():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": HEADERS["User-Agent"]})
            with urllib.request.urlopen(req, timeout=10) as r:
                ok(f"{name}: {r.status} — {url}")
        except urllib.error.HTTPError as e:
            err(f"{name}: HTTP {e.code} — {url}")
            all_ok = False
        except Exception as e:
            err(f"{name}: {str(e)[:60]} — {url}")
            all_ok = False
    return all_ok

def update_research_log(notes=None):
    """Append a timestamped entry to RESEARCH_LOG.md"""
    log_path = REPO / "RESEARCH_LOG.md"
    if not log_path.exists():
        return
    ts    = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"\n**{ts}** — deploy.py run"
    if notes:
        entry += f" — {notes}"
    entry += "\n"
    content = log_path.read_text()
    # Insert after first --- separator
    content = content.replace("---\n\n## 2026-04-23", f"---\n{entry}\n## 2026-04-23", 1)
    log_path.write_text(content)

def main():
    args = sys.argv[1:]

    print(f"\n{BOLD}badBANANA deploy.py{RESET}")
    print(f"  repo:  {REPO}")
    print(f"  paper: {PAPER}")
    print(f"  time:  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    paper_only  = "--paper"  in args
    github_only = "--github" in args
    check_only  = "--check"  in args
    commit_msg  = next((a.split("=",1)[1] for a in args if a.startswith("--msg=")), None)

    results = {}

    if check_only:
        check_live()
        return

    if paper_only:
        results["devto"] = devto_update()
    elif github_only:
        results["github"] = git_push(commit_msg)
    else:
        # Full deploy
        results["devto"]  = devto_update()
        results["github"] = git_push(commit_msg)
        results["live"]   = check_live()

    # Summary
    head("Deploy Summary")
    passed = sum(1 for v in results.values() if v)
    total  = len(results)
    for k, v in results.items():
        if v: ok(k)
        else: err(k)

    if passed == total:
        print(f"\n  {GREEN}{BOLD}All {total} targets deployed successfully.{RESET}\n")
    else:
        print(f"\n  {RED}{BOLD}{total - passed}/{total} targets failed.{RESET}\n")

if __name__ == "__main__":
    main()
