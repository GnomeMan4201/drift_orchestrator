import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from agent_runtime import AgentRuntime
from backend.mock_backend import MockBackend


BANNER = """
╔══════════════════════════════════════════════════════════════════╗
║       drift_orchestrator — OPERATOR VIEW  v0.8.0               ║
║  commands: /status  /log  /report  /reset  /quit               ║
║  input:    type message and press enter                         ║
╚══════════════════════════════════════════════════════════════════╝
"""


def run(backend=None, system_prompt=None):
    print(BANNER)
    if backend is None:
        backend = MockBackend(inject_bad_at=[3, 6, 9])

    runtime = AgentRuntime(backend=backend, verbose=True, system_prompt=system_prompt)

    while True:
        try:
            line = input("\n  › ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n[EXIT]")
            break

        if not line:
            continue

        if line in ("/quit", "/exit"):
            print("\n[EXIT]")
            break

        if line == "/status":
            runtime.status()
            continue

        if line == "/log":
            runtime.intervention_log()
            continue

        if line == "/report":
            runtime.report()
            continue

        if line == "/reset":
            runtime = AgentRuntime(backend=backend, verbose=True)
            continue

        if line == "/help":
            print("""
  /status   — session metrics
  /log      — intervention timeline
  /report   — full drift map
  /reset    — new session
  /quit     — exit
""")
            continue

        runtime.send(line)


if __name__ == "__main__":
    run()
