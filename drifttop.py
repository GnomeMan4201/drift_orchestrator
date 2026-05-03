#!/usr/bin/env python3
"""
drifttop.py
htop-style Textual TUI for drift_orchestrator.
Reads drift.db directly via sqlite3. No API required.

Usage:
    python3 drifttop.py
    python3 drifttop.py --db /path/to/drift.db
    python3 drifttop.py --refresh 2
"""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Label, RichLog, Static

DB_DEFAULT = Path.home() / "research_hub" / "repos" / "drift_orchestrator" / "data" / "drift.db"

ACTION_COLOR = {
    "CONTINUE":    "green",
    "INJECT":      "yellow",
    "REGENERATE":  "yellow",
    "ROLLBACK":    "red",
    "HALT":        "red bold",
}

SEVERITY_COLOR = {
    "HIGH":   "red",
    "MEDIUM": "yellow",
    "LOW":    "dim",
}


def _bar(v: float, w: int = 24) -> str:
    v = max(0.0, min(1.0, v))
    filled = round(v * w)
    return "[" + "#" * filled + "." * (w - filled) + "]"


def _alpha_color(a: float) -> str:
    if a >= 0.6:
        return "red"
    if a >= 0.35:
        return "yellow"
    return "green"


def _short_id(sid: str) -> str:
    return sid[:8] if sid else "?"


@dataclass
class SessionRow:
    id: str
    label: str
    alpha: float
    action: str
    turn_count: int
    total_tokens: int
    created_at: str


@dataclass
class SignalSummary:
    alpha: float = 0.0
    d_anchor: float = 0.0
    d_goal: float = 0.0
    rho: float = 0.0
    repetition: float = 0.0
    session_count: int = 0
    high_findings: int = 0
    medium_findings: int = 0


@dataclass
class Finding:
    severity: str
    finding_type: str
    detail: str
    session_id: str
    created_at: str


def _load(db_path: Path) -> tuple[SignalSummary, list[SessionRow], list[Finding]]:
    if not db_path.exists():
        return SignalSummary(), [], []

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Per-session latest alpha, action, turns
    rows = conn.execute("""
        SELECT
            s.id,
            COALESCE(s.session_label, '') as label,
            s.created_at,
            (SELECT tm.alpha
             FROM turn_metrics tm
             WHERE tm.session_id = s.id
             ORDER BY tm.created_at DESC LIMIT 1) as alpha,
            (SELECT tm.d_anchor
             FROM turn_metrics tm
             WHERE tm.session_id = s.id
             ORDER BY tm.created_at DESC LIMIT 1) as d_anchor,
            (SELECT tm.d_goal
             FROM turn_metrics tm
             WHERE tm.session_id = s.id
             ORDER BY tm.created_at DESC LIMIT 1) as d_goal,
            (SELECT tm.rho_density
             FROM turn_metrics tm
             WHERE tm.session_id = s.id
             ORDER BY tm.created_at DESC LIMIT 1) as rho,
            (SELECT tm.repetition_score
             FROM turn_metrics tm
             WHERE tm.session_id = s.id
             ORDER BY tm.created_at DESC LIMIT 1) as repetition,
            (SELECT pe.action
             FROM policy_events pe
             WHERE pe.session_id = s.id
             ORDER BY pe.created_at DESC LIMIT 1) as action,
            (SELECT COUNT(*) FROM turns t WHERE t.session_id = s.id) as turn_count,
            (SELECT COALESCE(SUM(t.token_count), 0)
             FROM turns t WHERE t.session_id = s.id) as total_tokens
        FROM sessions s
        ORDER BY s.created_at DESC
        LIMIT 30
    """).fetchall()

    sessions: list[SessionRow] = []
    total_alpha = total_anchor = total_goal = total_rho = total_rep = 0.0
    count = 0

    for r in rows:
        a = r["alpha"] or 0.0
        sessions.append(SessionRow(
            id=r["id"],
            label=r["label"] or r["id"][:8],
            alpha=a,
            action=r["action"] or "---",
            turn_count=r["turn_count"] or 0,
            total_tokens=r["total_tokens"] or 0,
            created_at=r["created_at"] or "",
        ))
        if r["alpha"] is not None:
            total_alpha  += r["alpha"] or 0.0
            total_anchor += r["d_anchor"] or 0.0
            total_goal   += r["d_goal"] or 0.0
            total_rho    += r["rho"] or 0.0
            total_rep    += r["repetition"] or 0.0
            count += 1

    # Findings summary
    fc = conn.execute("""
        SELECT severity, COUNT(*) as n
        FROM findings
        GROUP BY severity
    """).fetchall()
    high_f = sum(r["n"] for r in fc if r["severity"] == "HIGH")
    med_f  = sum(r["n"] for r in fc if r["severity"] == "MEDIUM")

    # Recent findings
    finding_rows = conn.execute("""
        SELECT severity, finding_type, detail, session_id, created_at
        FROM findings
        ORDER BY created_at DESC
        LIMIT 15
    """).fetchall()

    conn.close()

    div = max(count, 1)
    summary = SignalSummary(
        alpha       = total_alpha  / div,
        d_anchor    = total_anchor / div,
        d_goal      = total_goal   / div,
        rho         = total_rho    / div,
        repetition  = total_rep    / div,
        session_count = len(sessions),
        high_findings = high_f,
        medium_findings = med_f,
    )

    findings = [
        Finding(
            severity=r["severity"],
            finding_type=r["finding_type"],
            detail=r["detail"] or "",
            session_id=r["session_id"],
            created_at=(r["created_at"] or "")[:19],
        )
        for r in finding_rows
    ]

    return summary, sessions, findings


class SignalPanel(Static):
    """Top panel: htop-style signal bars."""

    def update_signals(self, s: SignalSummary) -> None:
        ac = _alpha_color(s.alpha)
        lines = [
            f"  [bold]alpha   [/bold] [{ac}]{_bar(s.alpha)}[/{ac}]  [{ac}]{s.alpha:.4f}[/{ac}]",
            f"  [bold]d_anchor[/bold] [yellow]{_bar(s.d_anchor)}[/yellow]  {s.d_anchor:.4f}",
            f"  [bold]d_goal  [/bold] [cyan]{_bar(s.d_goal)}[/cyan]  {s.d_goal:.4f}",
            f"  [bold]rho     [/bold] [blue]{_bar(s.rho)}[/blue]  {s.rho:.4f}",
            f"  [bold]repeat  [/bold] [magenta]{_bar(s.repetition)}[/magenta]  {s.repetition:.4f}",
        ]
        self.update("\n".join(lines))


class SummaryBar(Static):
    """Single-line status bar between signals and session table."""

    def update_summary(self, s: SignalSummary, db_path: Path) -> None:
        hc = "red" if s.high_findings else "dim"
        mc = "yellow" if s.medium_findings else "dim"
        self.update(
            f"  Sessions: [bold]{s.session_count}[/bold]"
            f"   Findings: [{hc}]{s.high_findings}H[/{hc}]"
            f" [{mc}]{s.medium_findings}M[/{mc}]"
            f"   Mean alpha: [{_alpha_color(s.alpha)}]{s.alpha:.4f}[/{_alpha_color(s.alpha)}]"
            f"   [dim]{db_path.name}[/dim]"
        )


class FindingsFeed(RichLog):
    """Bottom panel: recent findings feed."""

    def load_findings(self, findings: list[Finding]) -> None:
        self.clear()
        if not findings:
            self.write("[dim]no findings[/dim]")
            return
        for f in findings:
            sc = SEVERITY_COLOR.get(f.severity, "dim")
            detail = f.detail[:80] + ("..." if len(f.detail) > 80 else "")
            self.write(
                f"[{sc}]{f.severity:<6}[/{sc}]"
                f" [bold]{f.finding_type}[/bold]"
                f"  [dim]{_short_id(f.session_id)}[/dim]"
                f"  {detail}"
            )


class DriftTop(App):
    """drifttop: htop-style drift_orchestrator monitor."""

    CSS = """
Screen {
    background: $background;
}
SignalPanel {
    height: 7;
    border: solid $primary-darken-2;
    padding: 0 1;
}
SummaryBar {
    height: 1;
    background: $primary-darken-3;
    color: $text;
}
#session-table {
    height: 1fr;
}
FindingsFeed {
    height: 10;
    border: solid $primary-darken-2;
}
"""

    BINDINGS = [
        Binding("q", "quit", "quit"),
        Binding("r", "refresh_now", "refresh"),
        Binding("1", "sort_alpha", "sort alpha"),
        Binding("2", "sort_action", "sort action"),
        Binding("3", "sort_turns", "sort turns"),
    ]

    def __init__(self, db_path: Path, refresh_interval: float = 1.0) -> None:
        super().__init__()
        self.db_path = db_path
        self.refresh_interval = refresh_interval
        self._sort_key = "alpha"
        self._sessions: list[SessionRow] = []

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield SignalPanel(id="signals")
        yield SummaryBar(id="summary")
        yield DataTable(id="session-table", cursor_type="row", zebra_stripes=True)
        yield FindingsFeed(id="findings", highlight=True, markup=True, auto_scroll=False)
        yield Footer()

    def on_mount(self) -> None:
        t = self.query_one("#session-table", DataTable)
        t.add_columns(
            "SESSION", "LABEL", "ALPHA", "ACTION",
            "TURNS", "TOKENS", "STARTED"
        )
        self._load_data()
        self.set_interval(self.refresh_interval, self._load_data)

    @work(thread=True)
    def _load_data(self) -> None:
        summary, sessions, findings = _load(self.db_path)
        self.app.call_from_thread(self._apply, summary, sessions, findings)

    def _apply(
        self,
        summary: SignalSummary,
        sessions: list[SessionRow],
        findings: list[Finding],
    ) -> None:
        self._sessions = sessions

        self.query_one(SignalPanel).update_signals(summary)
        self.query_one(SummaryBar).update_summary(summary, self.db_path)
        self.query_one(FindingsFeed).load_findings(findings)
        self._refresh_table()

    def _refresh_table(self) -> None:
        t = self.query_one("#session-table", DataTable)
        t.clear()

        key = self._sort_key
        if key == "alpha":
            rows = sorted(self._sessions, key=lambda r: r.alpha, reverse=True)
        elif key == "action":
            rows = sorted(self._sessions, key=lambda r: r.action)
        else:
            rows = sorted(self._sessions, key=lambda r: r.turn_count, reverse=True)

        for r in rows:
            ac = ACTION_COLOR.get(r.action, "white")
            vc = _alpha_color(r.alpha)
            t.add_row(
                _short_id(r.id),
                r.label[:20],
                f"[{vc}]{r.alpha:.4f}[/{vc}]",
                f"[{ac}]{r.action}[/{ac}]",
                str(r.turn_count),
                str(r.total_tokens),
                r.created_at[:16].replace("T", " "),
            )

    def action_refresh_now(self) -> None:
        self._load_data()

    def action_sort_alpha(self) -> None:
        self._sort_key = "alpha"
        self._refresh_table()

    def action_sort_action(self) -> None:
        self._sort_key = "action"
        self._refresh_table()

    def action_sort_turns(self) -> None:
        self._sort_key = "turns"
        self._refresh_table()


def main() -> None:
    parser = argparse.ArgumentParser(description="drifttop: drift_orchestrator monitor")
    parser.add_argument("--db", type=Path, default=DB_DEFAULT, help="path to drift.db")
    parser.add_argument("--refresh", type=float, default=1.0, help="refresh interval in seconds")
    args = parser.parse_args()

    if not args.db.exists():
        print(f"ERROR: drift.db not found at {args.db}")
        print(f"Use --db /path/to/drift.db")
        raise SystemExit(1)

    app = DriftTop(db_path=args.db, refresh_interval=args.refresh)
    app.run()


if __name__ == "__main__":
    main()
