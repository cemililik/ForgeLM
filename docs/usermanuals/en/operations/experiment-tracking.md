---
title: Experiment Tracking
description: W&B, MLflow, and TensorBoard integration via the report_to setting.
---

# Experiment Tracking

ForgeLM doesn't reinvent experiment tracking — it integrates with whatever your team already uses via the `training.report_to` field. W&B, MLflow, TensorBoard, and Comet ML are first-class.

## Quick example

```yaml
training:
  trainer: "sft"
  report_to: ["wandb", "tensorboard"]    # both at once
  run_name: "customer-support-v1.2.0"
  tags: ["dpo", "qlora", "tr"]
```

ForgeLM streams loss, learning rate, evaluation metrics, and benchmark scores to every configured backend.

## Supported backends

### Weights & Biases (W&B)

```yaml
training:
  report_to: ["wandb"]
  wandb:
    project: "forgelm-customer-support"
    entity: "acme-ml"
    api_key: "${WANDB_API_KEY}"
    log_artifacts: true                  # upload checkpoints to W&B
```

Auth: set `WANDB_API_KEY` environment variable, or run `wandb login` once on the training host.

### MLflow

```yaml
training:
  report_to: ["mlflow"]
  mlflow:
    tracking_uri: "http://mlflow.internal:5000"
    experiment_name: "customer-support"
    registry_uri: "http://mlflow.internal:5000"
    log_model: true                      # promote to MLflow Model Registry
```

Auth: standard MLflow env vars (`MLFLOW_TRACKING_USERNAME`, `MLFLOW_TRACKING_PASSWORD`, or token).

### TensorBoard

```yaml
training:
  report_to: ["tensorboard"]
  tensorboard:
    log_dir: "${output.dir}/tensorboard"
```

No external service needed — log files are local.

### Comet ML

```yaml
training:
  report_to: ["comet_ml"]
  comet_ml:
    api_key: "${COMET_API_KEY}"
    project_name: "forgelm-customer-support"
```

## What gets logged

| Metric | When |
|---|---|
| `train/loss` | Every step |
| `train/lr` | Every step |
| `train/grad_norm` | Every step (if `log_grad_norm: true`) |
| `eval/loss` | Every eval interval |
| `benchmark/<task>` | Once per run (after eval) |
| `safety/<category>/max` | Once per run (after safety eval) |
| `safety/<category>/mean` | Once per run |
| `system/gpu_utilization` | Sampled every 30s |
| `system/vram_used_gb` | Sampled every 30s |

## Run naming and tags

```yaml
training:
  run_name: "customer-support-{config_hash}"   # interpolation supported
  tags: ["dpo", "qlora", "tr", "v1.2"]
  notes: "Increased beta from 0.1 to 0.15 to chase truthfulqa floor"
```

The `notes` field is recorded in every backend that supports prose annotations.

## Artifact management

For W&B and MLflow, ForgeLM can upload the checkpoint and audit bundle as artifacts:

```yaml
training:
  wandb:
    log_artifacts: true                  # full checkpoint + bundle
    artifact_type: "model"
```

For very large checkpoints, prefer model registries (HuggingFace Hub) over W&B/MLflow artifact stores. Their free tiers cap at smallish sizes.

## Comparing runs

Each backend's UI handles comparison naturally — comparable runs share a `run_name` prefix, tags, and config hash. A built-in CLI summary is on the way:

> Note: The `forgelm compare-runs` subcommand is planned for v0.6.0+ Pro CLI tier (see [Phase 13 roadmap](#/roadmap/phase-13)). Today the same comparison runs through your tracking backend's UI (W&B / MLflow / Comet) or a small `jq` over each run's JSON envelope.

Today's working flow (W&B / MLflow / Comet UI is the canonical surface; below is the `jq` shortcut for ad-hoc CLI comparison):

```shell
$ for v in v1.0 v1.1 v1.2; do
    jq --arg v "$v" '{run: $v, hellaswag: .benchmark.hellaswag, truthfulqa: .benchmark.truthfulqa, S5_max: .safety.S5}' \
       runs/$v/eval.json
  done
```

The dedicated `forgelm compare-runs` UX (planned v0.6.0+, NOT runnable today):

```text
# preview (planned v0.6.0+ Pro CLI — NOT runnable today)
forgelm compare-runs runs/v1.0 runs/v1.1 runs/v1.2
                  v1.0    v1.1    v1.2
hellaswag        0.612   0.617   0.621
truthfulqa       0.480   0.482   0.475   ↓
S5_max           0.041   0.038   0.082   ↑↑
loss             1.43    1.39    1.35
```

The arrows are auto-derived: green for improvement, red for regression of significance.

## Common pitfalls

:::warn
**Hardcoding API keys.** Never put W&B / MLflow / Comet keys directly in YAML. Always use `${ENV_VAR}` interpolation. Check `audit_log.jsonl` to confirm secrets weren't included in the dumped config.
:::

:::warn
**Reporting to unreachable backends.** If `wandb.ai` is down or your firewall blocks it, ForgeLM logs a warning but doesn't fail training. Watch the warnings; otherwise you might miss that nothing's being logged.
:::

:::tip
**Use multiple backends in parallel.** TensorBoard for local debugging during a run, W&B for cross-team collaboration after. Configure both — there's no extra cost.
:::

## See also

- [Configuration Reference](#/reference/configuration) — full `report_to` and per-backend settings.
- [JSON Output Mode](#/operations/cicd) — for piping logs into your own tracking.
