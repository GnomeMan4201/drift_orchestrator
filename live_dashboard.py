"""
live_dashboard.py
=================
Curses terminal dashboard consuming one or more SSE streams.

Usage:
    python live_dashboard.py --url http://localhost:8765/stream

Multiple streams:
    python live_dashboard.py \
        --url http://host1:8765/stream --label "node-1" \
        --url http://host2:8765/stream --label "node-2"

Keys while running:
    q / ESC / ^C  — quit
    r             — force reconnect all streams
"""

from __future__ import annotations

import argparse
import collections
import curses
import json
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Data model for one stream's state
# ---------------------------------------------------------------------------

@dataclass
class StreamState:
    url: str
    label: str
    connected: bool = False
    error: str = ""
    seq: int = 0
    alpha: float = 0.0
    external: float = 0.0
    divergence: float = 0.0
    policy_action: str = "—"
    reason: str = ""
    last_update: float = 0.0
    history: Deque[dict] = field(default_factory=lambda: collections.deque(maxlen=20))
    sparkline_alpha: Deque[float] = field(default_factory=lambda: collections.deque(maxlen=30))
    sparkline_div: Deque[float] = field(default_factory=lambda: collections.deque(maxlen=30))


# ---------------------------------------------------------------------------
# SSE reader (runs in a daemon thread per stream)
# ---------------------------------------------------------------------------

RECONNECT_DELAY = 3.0  # seconds between reconnect attempts
SPARK_CHARS = " ▁▂▃▄▅▆▇█"


def _sse_thread(state: StreamState, stop_event: threading.Event) -> None:
    """Daemon thread: connects to SSE URL, parses events, updates StreamState."""
    while not stop_event.is_set():
        try:
            req = urllib.request.Request(
                state.url,
                headers={"Accept": "text/event-stream", "Cache-Control": "no-cache"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                state.connected = True
                state.error = ""
                buf = b""
                while not stop_event.is_set():
                    chunk = resp.read(1)
                    if not chunk:
                        break
                    buf += chunk
                    if buf.endswith(b"\n\n"):
                        _parse_sse_block(buf.decode("utf-8", errors="replace"), state)
                        buf = b""
        except Exception as exc:
            state.connected = False
            state.error = str(exc)[:80]
        if not stop_event.is_set():
            time.sleep(RECONNECT_DELAY)
    state.connected = False


def _parse_sse_block(block: str, state: StreamState) -> None:
    for line in block.splitlines():
        if line.startswith("data:"):
            payload = line[5:].strip()
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                return
            state.seq = data.get("seq", state.seq)
            state.alpha = data.get("alpha", state.alpha)
            state.external = data.get("external", state.external)
            state.divergence = data.get("divergence", state.divergence)
            state.policy_action = data.get("policy_action", state.policy_action)
            state.reason = data.get("reason", state.reason)
            state.last_update = time.time()
            state.history.appendleft(
                {
                    "seq": state.seq,
                    "alpha": state.alpha,
                    "div": state.divergence,
                    "action": state.policy_action,
                    "ts": state.last_update,
                }
            )
            state.sparkline_alpha.append(state.alpha)
            state.sparkline_div.append(state.divergence)


# ---------------------------------------------------------------------------
# Sparkline renderer
# ---------------------------------------------------------------------------

def _sparkline(values: Deque[float], width: int = 20) -> str:
    if not values:
        return " " * width
    recent = list(values)[-width:]
    mn, mx = 0.0, 1.0  # normalise to [0,1] range
    span = mx - mn or 1.0
    chars = []
    for v in recent:
        idx = int((v - mn) / span * (len(SPARK_CHARS) - 1))
        idx = max(0, min(len(SPARK_CHARS) - 1, idx))
        chars.append(SPARK_CHARS[idx])
    # pad left
    return " " * (width - len(chars)) + "".join(chars)


# ---------------------------------------------------------------------------
# Colour pairs (initialised in _init_colors)
# ---------------------------------------------------------------------------

CP_NORMAL  = 0
CP_HEADER  = 1
CP_GOOD    = 2
CP_WARN    = 3
CP_DANGER  = 4
CP_LABEL   = 5
CP_DIM     = 6


def _init_colors() -> None:
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(CP_HEADER, curses.COLOR_CYAN,    -1)
    curses.init_pair(CP_GOOD,   curses.COLOR_GREEN,   -1)
    curses.init_pair(CP_WARN,   curses.COLOR_YELLOW,  -1)
    curses.init_pair(CP_DANGER, curses.COLOR_RED,     -1)
    curses.init_pair(CP_LABEL,  curses.COLOR_WHITE,   -1)
    curses.init_pair(CP_DIM,    curses.COLOR_BLACK,   -1)


def _action_color(action: str) -> int:
    return {
        "CONTINUE":   curses.color_pair(CP_GOOD),
        "INJECT":     curses.color_pair(CP_WARN),
        "REGENERATE": curses.color_pair(CP_WARN) | curses.A_BOLD,
        "ROLLBACK":   curses.color_pair(CP_DANGER) | curses.A_BOLD,
    }.get(action, curses.color_pair(CP_NORMAL))


def _div_color(divergence: float) -> int:
    if divergence >= 0.60:
        return curses.color_pair(CP_DANGER) | curses.A_BOLD
    if divergence >= 0.40:
        return curses.color_pair(CP_WARN)
    return curses.color_pair(CP_GOOD)


# ---------------------------------------------------------------------------
# Safe addstr helper
# ---------------------------------------------------------------------------

def _safe_addstr(win, row: int, col: int, text: str, attr: int = 0) -> None:
    h, w = win.getmaxyx()
    if row < 0 or row >= h or col < 0:
        return
    max_len = w - col - 1
    if max_len <= 0:
        return
    try:
        win.addstr(row, col, text[:max_len], attr)
    except curses.error:
        pass


# ---------------------------------------------------------------------------
# Main curses loop
# ---------------------------------------------------------------------------

def _draw(stdscr, states: List[StreamState]) -> None:
    _init_colors()
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.timeout(200)

    while True:
        key = stdscr.getch()
        if key in (ord("q"), ord("Q"), 27):  # q / ESC
            return
        if key == ord("r"):
            for s in states:
                s.connected = False
                s.error = "manual reconnect"

        stdscr.erase()
        h, w = stdscr.getmaxyx()
        now = time.time()

        # ── Header ─────────────────────────────────────────────────────────
        title = " drift_orchestrator — LIVE SIGNAL DASHBOARD "
        ts_str = time.strftime("%H:%M:%S")
        _safe_addstr(stdscr, 0, 0, title.center(w), curses.color_pair(CP_HEADER) | curses.A_BOLD)
        _safe_addstr(stdscr, 0, w - len(ts_str) - 1, ts_str, curses.color_pair(CP_DIM))

        row = 2
        panel_h = max(12, (h - 4) // len(states))

        for s in states:
            if row >= h - 2:
                break

            # ── Stream label + connection ───────────────────────────────
            conn_str = "● CONNECTED" if s.connected else "○ DISCONNECTED"
            conn_attr = curses.color_pair(CP_GOOD) if s.connected else curses.color_pair(CP_DANGER)
            _safe_addstr(stdscr, row, 0, f"  [{s.label}]  {s.url}", curses.color_pair(CP_LABEL) | curses.A_BOLD)
            _safe_addstr(stdscr, row, w - len(conn_str) - 2, conn_str, conn_attr)
            row += 1

            if s.error and not s.connected:
                _safe_addstr(stdscr, row, 4, f"error: {s.error}", curses.color_pair(CP_DANGER))
                row += 1

            # ── Scores ──────────────────────────────────────────────────
            age = now - s.last_update if s.last_update else 0
            age_str = f"seq={s.seq}  updated {age:.1f}s ago"
            _safe_addstr(stdscr, row, 4, age_str, curses.color_pair(CP_DIM))
            row += 1

            alpha_bar   = f"  alpha     : {s.alpha:.4f}"
            ext_bar     = f"  external  : {s.external:.4f}"
            div_bar     = f"  divergence: {s.divergence:.4f}"
            action_bar  = f"  policy    : {s.policy_action}"

            _safe_addstr(stdscr, row, 0, alpha_bar)
            row += 1
            _safe_addstr(stdscr, row, 0, ext_bar)
            row += 1
            _safe_addstr(stdscr, row, 0, div_bar, _div_color(s.divergence))
            row += 1
            _safe_addstr(stdscr, row, 0, action_bar, _action_color(s.policy_action))
            _safe_addstr(stdscr, row, 30, f"  {s.reason[:w-32]}", curses.color_pair(CP_DIM))
            row += 1

            # ── Sparklines ──────────────────────────────────────────────
            spark_w = min(30, w - 20)
            alpha_spark = _sparkline(s.sparkline_alpha, spark_w)
            div_spark   = _sparkline(s.sparkline_div,   spark_w)
            _safe_addstr(stdscr, row, 4, f"α trend: [{alpha_spark}]", curses.color_pair(CP_GOOD))
            row += 1
            _safe_addstr(stdscr, row, 4, f"Δ trend: [{div_spark}]", _div_color(s.divergence))
            row += 1

            # ── Recent history ──────────────────────────────────────────
            hist_rows = min(4, panel_h - 8, h - row - 2)
            if hist_rows > 0:
                _safe_addstr(stdscr, row, 4, "recent:", curses.color_pair(CP_DIM))
                row += 1
                for i, ev in enumerate(list(s.history)[:hist_rows]):
                    if row >= h - 1:
                        break
                    age_ev = now - ev.get("ts", now)
                    line = (
                        f"    seq={ev.get('seq',0):4d}  "
                        f"α={ev.get('alpha',0):.3f}  "
                        f"Δ={ev.get('div',0):.3f}  "
                        f"{ev.get('action',''):12s}  "
                        f"{age_ev:5.1f}s ago"
                    )
                    attr = _action_color(ev.get("action", ""))
                    _safe_addstr(stdscr, row, 0, line, attr)
                    row += 1

            # ── Separator ───────────────────────────────────────────────
            _safe_addstr(stdscr, row, 0, "─" * (w - 1), curses.color_pair(CP_DIM))
            row += 1

        # ── Footer ─────────────────────────────────────────────────────────
        footer = "  [q] quit   [r] reconnect"
        _safe_addstr(stdscr, h - 1, 0, footer, curses.color_pair(CP_DIM))

        stdscr.refresh()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="drift_orchestrator live signal dashboard"
    )
    parser.add_argument(
        "--url",
        dest="urls",
        action="append",
        default=[],
        metavar="URL",
        help="SSE stream URL (repeatable)",
    )
    parser.add_argument(
        "--label",
        dest="labels",
        action="append",
        default=[],
        metavar="LABEL",
        help="Label for each URL (repeatable, positional match)",
    )
    args = parser.parse_args()

    urls = args.urls or ["http://localhost:8765/stream"]
    labels = args.labels

    # Pad labels to match urls
    while len(labels) < len(urls):
        labels.append(f"stream-{len(labels)+1}")

    states = [
        StreamState(url=u, label=l)
        for u, l in zip(urls, labels)
    ]

    stop_event = threading.Event()
    threads = []
    for s in states:
        t = threading.Thread(target=_sse_thread, args=(s, stop_event), daemon=True)
        t.start()
        threads.append(t)

    try:
        curses.wrapper(_draw, states)
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()


if __name__ == "__main__":
    main()
