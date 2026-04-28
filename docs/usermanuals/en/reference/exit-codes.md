---
title: Exit Codes
description: ForgeLM's exit-code contract — the public API for CI/CD pipelines.
---

# Exit Codes

ForgeLM's exit codes are a public contract. CI/CD pipelines, schedulers, and dashboards depend on them. They will not silently change between releases.

## The contract

| Exit | Name | Meaning | Typical CI action |
|---|---|---|---|
| **0** | Success | Run completed; all gates passed; checkpoint promoted. | Continue pipeline |
| **1** | Config error | YAML invalid, file missing, env var unset, or argument malformed. | Fail fast |
| **2** | Audit warnings | Audit ran with `--strict` and reported warning-level issues. | Block merge / require review |
| **3** | Regression / auto-revert | Benchmark or safety gate failed; auto-reverted. | Investigate; do NOT promote |
| **4** | Awaiting human approval | `compliance.human_approval: true` blocking. | Hold pipeline; trigger reviewer |
| **5** | Cost ceiling exceeded | `output.cost_tracking.halt_threshold_usd` crossed. | Investigate cost overrun |
| **130** | Interrupted | User pressed Ctrl+C. | Manual decision |

Any other non-zero exit indicates an unexpected error — file an issue.

## Mapping to CI patterns

### GitHub Actions

```yaml
- name: Train
  id: train
  run: forgelm --config configs/run.yaml
  continue-on-error: true

- name: Block on regression
  if: steps.train.outcome == 'failure' && steps.train.conclusion == 'failure'
  run: |
    if [ "${{ steps.train.outputs.exit-code }}" = "3" ]; then
      echo "::error::Regression detected — see audit log"
      exit 1
    fi
```

For most pipelines, the simpler pattern is fine:

```yaml
- name: Train
  run: forgelm --config configs/run.yaml
  # Any non-zero exit fails the step. The artifact upload step still runs (if: always()).
```

### GitLab CI

```yaml
train:
  script:
    - forgelm --config configs/run.yaml
  allow_failure:
    exit_codes: [4]                    # exit 4 (waiting for approval) doesn't fail CI
```

### Jenkins

```groovy
stage('Train') {
  steps {
    script {
      def status = sh(script: 'forgelm --config configs/run.yaml', returnStatus: true)
      if (status == 4) {
        currentBuild.result = 'UNSTABLE'   // hold for approval
      } else if (status != 0) {
        error "Training failed with exit code ${status}"
      }
    }
  }
}
```

## When to use each exit code

| Situation | What ForgeLM exits with |
|---|---|
| YAML has typo (e.g. `learnng_rate`) | 1 |
| `${HF_TOKEN}` set in YAML but env var missing | 1 |
| `--config` points to non-existent file | 1 |
| Audit with `--strict` and PII flags | 2 |
| Audit with `--strict` and cross-split leakage | 3 (cross-split is error, not warning) |
| DPO run, Llama Guard S5 regressed beyond tolerance | 3 |
| Benchmark hellaswag dropped below floor | 3 |
| Final loss is NaN | 3 |
| `compliance.human_approval: true` and no approval signed | 4 |
| Cost threshold crossed mid-training | 5 |
| User Ctrl+C | 130 |

## Programmatic determination

For automated parsing, ForgeLM also writes the exit code to a sidecar file:

```text
checkpoints/run/artifacts/exit_status.txt:

3
trigger=safety_regression
regressed_categories=S5
restored_from=./checkpoints/sft-base
```

This is helpful when CI runners stream output to log aggregation that doesn't preserve raw exit codes (some Jenkins setups, certain GitOps tools). The sidecar is always written.

## What "exit 0" actually guarantees

A run that exits 0 has:
- Validated config without errors.
- Loaded the model and dataset.
- Completed all configured training steps.
- Passed every configured benchmark floor.
- Passed every configured safety threshold.
- Written the model card.
- Written the Annex IV bundle (if configured).
- Written manifest.json with SHA-256 over all artifacts.
- Optionally: written GGUF, deployment config.
- Closed the audit log with `run_complete`.

If any of these failed, the exit code is non-zero. There is no "partial success" exit code by design.

## Compatibility guarantee

Exit codes 0-5 are stable across versions. New codes may be added (6, 7, ...) but existing ones won't change semantics. CI pipelines pinned to the contract above will continue working across ForgeLM upgrades.

## See also

- [CI/CD Pipelines](#/operations/cicd) — patterns that use this contract.
- [CLI Reference](#/reference/cli) — every command that emits these codes.
- [Auto-Revert](#/evaluation/auto-revert) — produces exit 3.
- [Human Oversight](#/compliance/human-oversight) — produces exit 4.
