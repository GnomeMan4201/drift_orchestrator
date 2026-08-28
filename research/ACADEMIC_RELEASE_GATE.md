# Academic release gate: Second-Order Injection

Status: **not yet DOI-ready**

This gate separates the existing recorded evidence from the stronger claims required for an archival research release. It is deliberately fail-closed: a missing item remains visible and cannot be converted into a completed claim by prose alone.

## Frozen claim boundary

The current evidence supports this claim:

> In the recorded local evaluator architecture, attacker-influenced text placed in the evaluator's free-form context altered safety verdicts. The V4 reasoning-capture vector transferred across the three tested local model configurations, and symmetric manipulation reduced the coupled evaluator-divergence signal.

The current evidence does **not** support claims of universal exploitability, model-family-wide behavior, production prevalence, or defense sufficiency.

## Evidence already present

- paper-style technical report in `papers/second_order_injection.md`
- raw JSONL and derived summaries under `results/`
- phase 1, phase 2, transfer, mitigation, meta-evaluator, and adaptive probe scripts
- a public gateway adapter and `REPLICATE.md`
- explicit limitations and negative results
- independent-replication request in issue #3

## Release gates

| Gate | Requirement | Current status | Blocking reason |
|---|---|---|---|
| G1 claim control | Every headline claim maps to raw rows, denominator, script, and summary | Partial | No machine-readable claim-to-evidence ledger |
| G2 historical provenance | Repository commit, Python/Ollama versions, exact model identifiers and digests, hardware, parameters, and timestamps for the recorded runs | Blocked | Exact historical runtime/model identity was not captured consistently |
| G3 immutable artifact | Tagged release with SHA-256 manifest covering paper, scripts, raw results, summaries, and environment records | Open | No release manifest |
| G4 clean verification | Fresh environment verifies schemas, raw-to-summary derivation, and all non-model tests | Open | Deterministic artifact verifier is not yet a release gate |
| G5 statistical treatment | Raw denominators, error/skipped counts, uncertainty intervals, and effect estimates for each reported condition | Partial | Several conditions are small and reported mainly as percentages |
| G6 independent replication | At least one report from a person not involved in authoring, with raw outputs and environment manifest | Open | Issue #3 has no completed report |
| G7 literature position | Systematic related-work table distinguishing evaluator injection, indirect prompt injection, LLM-as-judge attacks, and monitor evasion | Open | Current report does not establish novelty against a frozen search record |
| G8 archival identity | Stable author name, ORCID, citation metadata, license, repository release, and DOI deposit metadata | Blocked | Publication identity and ORCID are not recorded here |
| G9 venue package | Anonymized or camera-ready paper, ethics statement, artifact appendix, and venue-specific checklist | Open | Venue not selected |

## Non-recoverable versus recoverable provenance

Historical model digests cannot be reconstructed reliably after the fact. Do not infer them from current Ollama tags.

Handle this boundary explicitly:

1. Label the committed runs **historical recorded evidence with incomplete environment provenance**.
2. Preserve their raw rows unchanged.
3. Run a new versioned replication series with complete environment manifests.
4. Report historical and fresh results separately.
5. Treat changed outcomes as observed model/runtime drift until evidence supports another explanation.

## Minimum DOI-ready package

```text
paper/
  second_order_injection.pdf
  artifact_appendix.md
artifact/
  MANIFEST.sha256
  claims.json
  environments/
  scripts/
  results/raw/
  results/derived/
  schemas/
  replication-reports/
CITATION.cff
LICENSE
README.md
```

The SHA-256 manifest must cover immutable bytes in the release archive. Generated timestamps, caches, local paths, and transient logs must not enter claim equality.

## Claim ledger requirements

Each empirical claim must record:

```yaml
claim_id:
statement:
scope:
script:
raw_files:
derived_files:
valid_n:
error_n:
skipped_n:
effect:
uncertainty:
environment_ids:
limitations:
status: supported | mixed | negative | superseded
```

A claim is release-valid only when the listed raw files exist, the derived value can be regenerated, and every environment ID resolves to a committed manifest.

## Statistical upgrade

For every binary bypass/detection condition:

- report successes and valid trials, not percentages alone;
- report timeout, parse-error, and skipped counts separately;
- add a Wilson 95% confidence interval;
- avoid treating sequential window steps as independent replicates;
- define the independent unit before collecting the next run;
- preserve per-run and pooled estimates;
- preregister the primary comparison for the fresh replication.

The next experiment should increase independent repetitions rather than only adding more correlated window steps.

## Execution order

1. Add schemas for environment manifests and claim records.
2. Build a deterministic verifier that regenerates summaries from raw JSONL.
3. Freeze the existing evidence as a provenance-limited historical artifact.
4. Capture a fully identified fresh environment.
5. Run a preregistered focused V4 replication with adequate independent repeats.
6. Obtain an external replication using the same report contract.
7. Freeze the literature review and narrow the novelty statement.
8. Add citation metadata after the publication name and ORCID are confirmed.
9. Tag the archival release and deposit that exact archive for a DOI.
10. Submit the paper to a focused security/AI-safety workshop.

## Merge rule

This document creates gates; it does not certify them. A gate may move to complete only in the same change that adds the referenced evidence or verifier.