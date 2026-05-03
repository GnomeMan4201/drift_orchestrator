# Control-Plane Event Contract

**Version:** 1.0  
**Status:** Authoritative  
**Last verified against:** drifttop.py, controlplane/invariants.py, controlplane/journal.py, controlplane/replay.py

This document is the single source of truth for the action vocabulary, event schema,
invariant rules, and UI status behavior of the drift_orchestrator control plane.
Patches to any of these files must keep this document in sync.

---

## 1. Architecture Map

```
drift_orchestrator SQLite (drift.db)
        |
        v
drifttop.py  [Textual TUI — operator surface]
        |
        | calls _log_action(action, target, result, metadata)
        v
controlplane/journal.py  [SQLite persistence — ~/.drift_controlplane/journal.db]
        |
        | recent_events(session_id) -> list[dict]
        v
controlplane/invariants.py  [rule evaluation — no I/O]
        |
        | check(events) -> list[Finding]
        | select_highest_severity_finding(findings) -> Finding
        | format_invariant_status(finding) -> str
        v
drifttop.py  ControlPlaneStatus widget  [live status bar in TUI]

        |
        | (on 'e' keypress or --report CLI flag)
        v
controlplane/replay.py
        |
        v
exports/action_log_<session_id>.jsonl
exports/session_<session_id>_report.md
```

---

## 2. Event Schema

Every operator action is persisted as one row in the `action_events` table
in `~/.drift_controlplane/journal.db`.

| Field            | Type    | Nullable | Description |
|------------------|---------|----------|-------------|
| `id`             | INTEGER | No       | Auto-increment primary key |
| `ts`             | TEXT    | No       | ISO-8601 UTC timestamp (e.g. `2026-05-03T18:12:01.234+00:00`) |
| `session_id`     | TEXT    | No       | Operator UI session — format `session_YYYYMMDD_HHMMSS` |
| `action`         | TEXT    | No       | Canonical action name (see section 3) |
| `target_type`    | TEXT    | Yes      | `"session"` when a drift session is the target; `None` otherwise |
| `target_id`      | TEXT    | Yes      | Drift session UUID (short form in display, full UUID in DB) |
| `target_summary` | TEXT    | Yes      | Human-readable: `"<label> alpha=<n> action=<policy>"` |
| `result`         | TEXT    | Yes      | `"ok"` \| `"error"` \| `"pending"` \| `"cancelled"` \| `"timeout"` |
| `metadata_json`  | TEXT    | Yes      | JSON blob with action-specific fields |

### Session ID format

```
session_20260503_181201
```

Generated once per TUI launch in `DriftTop.__init__`. Displayed in the Textual
header subtitle. Used as the grouping key for all invariant evaluations.

---

## 3. Canonical Action Names

These are the **exact string values** written to `action_events.action` by
`drifttop.py`. Do not use synonyms (`approve`, `fail`, `export_session_log`,
etc.) — the invariant rules match on these exact strings.

### Observation actions (no confirmation required)

| Action      | Trigger        | Target | Typical result |
|-------------|---------------|--------|----------------|
| `analyze`   | `a` key       | session | `ok` |
| `findings`  | `f` key       | session | `ok` |
| `open_raw`  | `o` key       | session | `ok` |

### Replay

| Action           | Trigger              | Target | Typical result |
|------------------|---------------------|--------|----------------|
| `replay`         | `R` key             | session | `ok` |
| `replay_complete`| worker thread exit  | None   | `ok` / `error` / `timeout` |

`replay_complete` carries `metadata={"exit_code": <int>}`.

### Promotion workflow (two-step: pending → confirm)

| Action                       | Trigger           | Target  | result      |
|------------------------------|------------------|---------|-------------|
| `promote_candidate_pending`  | `p` key          | session | `pending`   |
| `clamp_pending`              | `c` key          | session | `pending`   |
| `confirm_yes`                | `y` key          | None    | `ok`        |
| `confirm_no`                 | `n` key          | None    | `cancelled` |
| `clamp`                      | worker thread exit (after confirm_yes on clamp) | None | `ok` / `error` |

**Note:** `promote_candidate` (final completion) is not currently logged as a
distinct action. Only `promote_candidate_pending` is written at intent time.
`clamp` IS logged at completion with exit code in metadata.

`confirm_yes` carries `metadata={"confirmed_action": "promote"|"clamp", "session_id": <uuid>}`.  
`confirm_no` carries `metadata={"cancelled_action": "promote"|"clamp", "session_id": <uuid>}`.  
`clamp` carries `metadata={"annotation_path": <str>, "session_id": <uuid>, "exit_code": <int>}`.

### Export

| Action   | Trigger  | Target | result |
|----------|---------|--------|--------|
| `export` | `e` key | None   | `ok`   |

`export` carries `metadata={"path": <str>, "event_count": <int>}`.

---

## 4. Result Semantics

| Value         | Meaning |
|---------------|---------|
| `"ok"`        | Action completed successfully. Default for all actions unless specified. |
| `"error"`     | Action failed. Triggers `fail_present` invariant. Maps to operator risk. |
| `"pending"` (`result="pending"`) | Intent recorded; awaiting confirmation. Does not trigger `fail_present`. |
| `"cancelled"` (`result="cancelled"`) | Operator pressed `n` to abort a pending action. |
| `"timeout"`   | Worker process exceeded time limit (replay harness). |

### How result="error" maps to fail_present

`invariants._fail_present` scans the event list for any event where
`e.get("result") == "error"`. It fires regardless of action name.
This means any action — `clamp`, `replay_complete`, or future actions —
that completes with `result="error"` will trigger the `fail_present` finding.

---

## 5. Invariant Rules

Rules are evaluated by `invariants.check(events)` over a **chronological**
(oldest-first) event list. All rules are implemented in `controlplane/invariants.py`.
No rule logic lives in drifttop.py or replay.py.

### clean_session

- **Severity:** pass
- **Trigger:** No other rule fired.
- **Code:** `clean_session`
- **Example:**

```
analyze   target=session:abc  result=ok
findings  target=session:abc  result=ok
export                        result=ok
→ [PASS clean_session]
```

---

### rollback_present

- **Severity:** warn
- **Trigger:** Any event where `"rollback" in action`.
- **Code:** `rollback_present`
- **Fires:** Once per matching event.
- **Example:**

```
analyze   target=session:abc  result=ok
rollback  target=session:abc  result=ok
→ [WARN rollback_present]
```

---

### fail_present

- **Severity:** warn
- **Trigger:** Any event where `result == "error"`.
- **Code:** `fail_present`
- **Fires:** Once per matching event.
- **Example:**

```
clamp  target=session:abc  result=error
→ [WARN fail_present]
```

---

### approve_then_fail_same_target

- **Severity:** warn
- **Trigger:** A `confirm_yes` event on target T is followed by a `result=error`
  event on the same target T. Order matters — error must come after confirm_yes.
- **Code:** `approve_then_fail_same_target`
- **Fires:** Once per violating target.
- **Example:**

```
confirm_yes  target_id=abc  result=ok
clamp        target_id=abc  result=error
→ [WARN approve_then_fail_same_target]
```

**Counter-example (does NOT fire):**

```
clamp        target_id=abc  result=error   ← error first
confirm_yes  target_id=abc  result=ok
→ [PASS clean_session]
```

---

### repeated_action_same_target

- **Severity:** warn
- **Trigger:** The same `(action, target_id)` pair appears >= 3 times.
- **Code:** `repeated_action_same_target`
- **Threshold:** 3 (default, not configurable at runtime).
- **Fires:** Once per violating `(action, target_id)` pair.
- **Example:**

```
analyze  target_id=abc
analyze  target_id=abc
analyze  target_id=abc    ← third occurrence hits threshold
→ [WARN repeated_action_same_target]
```

**Counter-example (does NOT fire):**

```
analyze  target_id=abc
analyze  target_id=def    ← different target, counts separately
analyze  target_id=ghi
→ [PASS clean_session]
```

---

### action_after_export

- **Severity:** warn
- **Trigger:** An `export` event exists and is not the last event in the session.
  Evaluated against the **last** export if multiple exist.
- **Code:** `action_after_export`
- **Fires:** Once per session (not per post-export action).
- **Example:**

```
analyze
export     ← export logged
analyze    ← action after export
→ [WARN action_after_export]
```

**Counter-example (does NOT fire):**

```
analyze
export     ← export is last
→ [PASS clean_session]
```

---

### promote_clamp_without_candidate

- **Severity:** warn
- **Trigger:** A `clamp` or `promote_clamp` event exists on target T, but no
  `promote_candidate` event exists for the same target T anywhere in the session.
- **Code:** `promote_clamp_without_candidate`
- **Fires:** Once per violating clamp event.
- **Example:**

```
clamp  target_id=abc
→ [WARN promote_clamp_without_candidate]
```

**Counter-example (does NOT fire):**

```
promote_candidate  target_id=abc
clamp              target_id=abc
→ [PASS clean_session]
```

---

### rollback_without_prior_approval

- **Severity:** warn
- **Trigger:** A `rollback` action (or any action containing `"rollback"`) occurs
  on target T without a prior `confirm_yes` on the same target T. Scanned
  forward in chronological order — a `confirm_yes` after the rollback does not
  retroactively clear the flag.
- **Code:** `rollback_without_prior_approval`
- **Fires:** Once per violating rollback event.
- **Example:**

```
rollback  target_id=abc   ← no prior confirm_yes for abc
→ [WARN rollback_without_prior_approval]
```

**Counter-example (does NOT fire):**

```
confirm_yes  target_id=abc
rollback     target_id=abc
→ [PASS clean_session]  (rollback_present still fires separately)
```

---

## 6. UI Status Behavior

### select_highest_severity_finding

```python
from controlplane.invariants import select_highest_severity_finding
top = select_highest_severity_finding(findings)
```

Selects the worst finding by severity priority:

```
fail (2) > warn (1) > pass (0)
```

Returns the canonical `_PASS` finding if the list is empty.
When multiple findings share the highest severity, the first one (earliest in
the findings list) is returned.

### format_invariant_status

Formats a single `Finding` into a one-line Rich markup string for the
`ControlPlaneStatus` widget:

```
Pass:   "  [dim]STATUS: PASS  session_evaluated[/dim]"
Warn:   "  [bold yellow]STATUS: WARN[/bold yellow]  [yellow]<code>[/yellow]  [dim]<message>[/dim]"
Fail:   "  [bold red]STATUS: FAIL[/bold red]  [red]<code>[/red]  [dim]<message>[/dim]"
```

Properties guaranteed by `test_controlplane_status_formatting.py`:
- Single line (no newlines).
- Balanced Rich markup brackets.
- Starts with two spaces for padding.
- PASS uses `[dim]`, never yellow or red.
- WARN uses `yellow`, FAIL uses `red`.

### ControlPlaneStatus widget

Positioned between `FindingsFeed` and `ActionLog` in the TUI layout.
Updated synchronously after every `_log_action` call via `_update_status_from_invariants`.
Status update errors are silently caught — a DB blip will never crash the TUI.

---

## 7. Known Gaps and Future Work

| Gap | Notes |
|-----|-------|
| `promote_candidate` (final) not logged | Only `promote_candidate_pending` is written. `_do_promote` completes without a journal entry. |
| `inspect_invariants` (`i` key) not logged | Deliberately omitted — read-only action, no state change. |
| `replay_complete` timeout detection | `exit_code == -1` maps to `result="timeout"` but no invariant rule checks for it yet. |
| Ollama narrative summary | Planned post-deterministic-summary layer. Pipeline: journal → replay → invariants → Ollama. |

---

## 8. Vocabulary Mismatch Reference

This table exists to prevent re-introduction of incorrect names in tests or patches.

| Wrong name (do not use) | Correct name | Why |
|------------------------|--------------|-----|
| `approve`              | `confirm_yes` | The TUI uses `y` for confirm, logged as `confirm_yes` |
| `fail`                 | `result="error"` on any action | `fail` is not an action name; failure is a result value |
| `export_session_log`   | `export`      | The logged action string is `"export"` |
| `export_not_final`     | `action_after_export` | Renamed for precision during invariants refactor |
| `empty_session`        | `clean_session` | The PASS finding code is `clean_session` |
