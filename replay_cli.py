#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Violation:
    rule: str
    detail: str
    event_index: int | None = None
    session_id: str | None = None
    checkpoint_id: str | None = None


@dataclass
class ReplayResult:
    audit_log_path: Path
    snapshot_dir: Path
    total_events: int = 0
    trigger_fired_count: int = 0
    snapshot_frozen_count: int = 0
    violations: list[Violation] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.violations

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "audit_log_path": str(self.audit_log_path),
            "snapshot_dir": str(self.snapshot_dir),
            "total_events": self.total_events,
            "trigger_fired_count": self.trigger_fired_count,
            "snapshot_frozen_count": self.snapshot_frozen_count,
            "violation_count": len(self.violations),
            "violations": [v.__dict__ for v in self.violations],
        }

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        lines = [
            f"[{status}] ACFC-Safe Audit Replay",
            f"  audit log   : {self.audit_log_path}",
            f"  snapshot dir: {self.snapshot_dir}",
            f"  total events: {self.total_events}",
            f"  TRIGGER_FIRED   : {self.trigger_fired_count}",
            f"  SNAPSHOT_FROZEN : {self.snapshot_frozen_count}",
            f"  violations      : {len(self.violations)}",
        ]
        for v in self.violations:
            loc = f" event={v.event_index}" if v.event_index is not None else ""
            lines.append(f"  - {v.rule}{loc}: {v.detail}")
        return "\n".join(lines)


def _key(event: dict) -> tuple[str | None, str | None]:
    return event.get("session_id"), event.get("checkpoint_id")


def verify_audit_log(audit_log_path: Path, snapshot_dir: Path) -> ReplayResult:
    result = ReplayResult(audit_log_path=audit_log_path, snapshot_dir=snapshot_dir)

    try:
        lines = audit_log_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        result.violations.append(
            Violation("AUDIT_LOG_MISSING", f"Audit log not found: {audit_log_path}")
        )
        return result
    except OSError as exc:
        result.violations.append(
            Violation("AUDIT_LOG_UNREADABLE", f"Audit log unreadable: {exc}")
        )
        return result

    frozen_seen: set[tuple[str | None, str | None]] = set()

    for idx, line in enumerate(lines):
        if not line.strip():
            continue

        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            result.violations.append(
                Violation("MALFORMED_JSONL", f"Invalid JSONL: {exc}", idx)
            )
            continue

        result.total_events += 1
        event_type = event.get("event_type")
        session_id, checkpoint_id = _key(event)

        if event_type == "SNAPSHOT_FROZEN":
            result.snapshot_frozen_count += 1
            frozen_seen.add((session_id, checkpoint_id))

            snap_path_raw = event.get("snapshot_path")
            if not snap_path_raw:
                result.violations.append(
                    Violation(
                        "RULE_2_MISSING_SNAPSHOT_PATH",
                        "SNAPSHOT_FROZEN has no snapshot_path",
                        idx,
                        session_id,
                        checkpoint_id,
                    )
                )
                continue

            snap_path = Path(snap_path_raw)
            if not snap_path.exists():
                result.violations.append(
                    Violation(
                        "RULE_2_SNAPSHOT_MISSING",
                        f"Snapshot file missing: {snap_path}",
                        idx,
                        session_id,
                        checkpoint_id,
                    )
                )
                continue

            try:
                data = json.loads(snap_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                result.violations.append(
                    Violation(
                        "RULE_3_SNAPSHOT_UNREADABLE",
                        f"Snapshot unreadable or invalid JSON: {exc}",
                        idx,
                        session_id,
                        checkpoint_id,
                    )
                )
                continue

            if data.get("rewrite_used") is not False:
                result.violations.append(
                    Violation(
                        "RULE_3_REWRITE_USED_NOT_FALSE",
                        "Snapshot rewrite_used is not false",
                        idx,
                        session_id,
                        checkpoint_id,
                    )
                )

        elif event_type == "TRIGGER_FIRED":
            result.trigger_fired_count += 1
            if (session_id, checkpoint_id) not in frozen_seen:
                result.violations.append(
                    Violation(
                        "RULE_1_NO_PRECEDING_SNAPSHOT_FROZEN",
                        "TRIGGER_FIRED occurred before SNAPSHOT_FROZEN",
                        idx,
                        session_id,
                        checkpoint_id,
                    )
                )

    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-log", default="storage/audit_log.jsonl")
    parser.add_argument("--snapshot-dir", default="storage/snapshots")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    result = verify_audit_log(Path(args.audit_log), Path(args.snapshot_dir))

    if args.as_json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(result.summary())

    if any(v.rule in {"AUDIT_LOG_MISSING", "AUDIT_LOG_UNREADABLE"} for v in result.violations):
        return 2

    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
