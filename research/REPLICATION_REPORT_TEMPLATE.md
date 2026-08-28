# Independent replication report: Second-Order Injection

This template is for a replication performed by someone who did not author the original experiment or its implementation.

## Report identity

- Replication level: repository verification / fresh model rerun
- Replicator:
- Affiliation or independent status:
- Contact or persistent identifier:
- Report date:
- Report license:
- Conflict or prior collaboration:

## Source identity

- Repository URL:
- Commit SHA:
- Release tag, if any:
- Artifact SHA-256:
- Local changes: none / attached diff
- Verification command:
- Verification result:

## Environment

Attach a completed environment manifest conforming to `research/schemas/environment-manifest.v1.schema.json`.

At minimum record:

- operating system and architecture;
- CPU, RAM, and accelerator;
- Python and dependency-lock identity;
- Ollama version;
- exact model names and digests;
- gateway configuration;
- decoding/sampling parameters;
- start and end timestamps;
- whether the environment was online or isolated.

Do not substitute a current model tag for an unknown historical digest.

## Protocol

- Probe scripts:
- Conditions:
- Independent repetition unit:
- Planned repetitions:
- Completed repetitions:
- Deviations from the published protocol:
- Deviations decided before or after inspecting outcomes:

## Results

For each condition, report counts rather than percentages alone.

| Condition | Successes | Valid trials | Errors | Skipped | Estimate | 95% interval |
|---|---:|---:|---:|---:|---:|---:|
| Clean baseline | | | | | | |
| V4 injection | | | | | | |
| Symmetric V4, if tested | | | | | | |
| Mitigation, if tested | | | | | | |

Attach raw result files and the exact derivation command. Do not edit raw model outputs to repair formatting; record parser behavior separately.

## Primary replication judgments

- Evaluator verdict manipulation reproduced: yes / no / mixed
- Cross-model transfer reproduced: yes / no / mixed / not tested
- Coupled divergence collapse reproduced: yes / no / mixed / not tested
- Reported vector ordering reproduced: yes / no / mixed / not tested
- Material contradiction found: yes / no
- Evidence strength: repository-only / qualitative rerun / quantitative rerun

## Differences from the recorded artifact

Describe:

- model or runtime drift;
- prompt or parser differences;
- changed valid-response denominators;
- hardware or inference differences;
- conditions whose direction changed;
- conditions that could not be evaluated.

A changed percentage is not by itself a contradiction. A direction reversal under a comparable, fully identified environment is material and should be highlighted.

## Negative and failed results

Record all failures, including:

- environment setup failures;
- model acquisition failures;
- timeouts;
- parse failures;
- conditions with insufficient valid responses;
- mitigation conditions that reduced utility or detection;
- analyses abandoned after results were observed.

## Artifact locations

- Environment manifest:
- Raw outputs:
- Derived summaries:
- Code diff:
- Logs:
- SHA-256 manifest:
- Permanent archive or DOI:

## Signed conclusion

State only what this run establishes. Separate direct observations from interpretation and universal claims.

> I verified that the attached report, environment manifest, raw outputs, and hashes describe the run I performed.

- Name:
- Date:
- Optional signature or signed-commit reference:
