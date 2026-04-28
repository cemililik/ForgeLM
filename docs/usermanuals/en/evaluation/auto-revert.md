---
title: Auto-Revert
description: Roll back to the last-good checkpoint when benchmarks or safety regress.
---

# Auto-Revert

A fine-tuned model that scores worse than its starting point on safety or quality is worse than no fine-tune. Auto-revert is ForgeLM's safety net: if any configured threshold fails after training, the run rolls back to the last-good checkpoint and emits a structured incident record.

## Decision flow

```mermaid
flowchart TD
    Start[Training complete]
    Bench{Benchmark<br/>floors pass?}
    Safety{Safety<br/>thresholds pass?}
    Loss{Final loss<br/>vs starting?}
    OK([Promote new checkpoint<br/>exit 0])
    Revert([Restore last-good<br/>exit 3])
    Audit[Append incident<br/>to audit log]

    Start --> Bench
    Bench -->|fail| Audit
    Bench -->|pass| Safety
    Safety -->|fail| Audit
    Safety -->|pass| Loss
    Loss -->|reasonable| OK
    Loss -->|exploded| Audit
    Audit --> Revert

    classDef ok fill:#1c2030,stroke:#22c55e,color:#e6e7ec
    classDef fail fill:#1c2030,stroke:#ef4444,color:#e6e7ec
    classDef question fill:#161a24,stroke:#0ea5e9,color:#e6e7ec
    class OK ok
    class Revert,Audit fail
    class Bench,Safety,Loss question
```

## What triggers a revert

| Signal | Threshold | Configurable via |
|---|---|---|
| Benchmark task below floor | Per-task `floors:` setting | `evaluation.benchmark.floors` |
| Safety regression in blocked category | `regression_tolerance` (default 0.05) | `evaluation.safety.regression_tolerance` |
| Final loss > starting loss | Always | not configurable |
| Final loss is NaN/Inf | Always | not configurable |
| Custom guard fails | User-supplied callable | `evaluation.guards.<name>` |

Any of these triggers a revert.

## What happens during a revert

1. ForgeLM identifies the last-good checkpoint — typically the SFT checkpoint when DPO failed, or the previous training run's output for a continued-training scenario.
2. Copies the last-good weights to the configured output directory (overwriting the bad ones).
3. Writes an incident record to `audit_log.jsonl`:

```json
{
  "ts": "2026-04-29T14:33:04Z",
  "event": "auto_revert",
  "trigger": "safety_regression",
  "regressed_categories": ["S5"],
  "baseline_safety": {"S5": {"max": 0.08}},
  "post_train_safety": {"S5": {"max": 0.42}},
  "restored_from": "./checkpoints/sft-base",
  "exit_code": 3
}
```

4. Optionally fires a webhook (Slack, Teams) — see [Webhooks](#/operations/webhooks).
5. Exits with code 3.

## Configuration

```yaml
evaluation:
  auto_revert:
    enabled: true
    last_good_checkpoint: "./checkpoints/sft-base"
    notify_on_revert: true              # fire webhook
    keep_failed_checkpoint: true        # also keep the bad one for inspection
    failed_checkpoint_dir: "./checkpoints/failed/"
```

If `last_good_checkpoint` is omitted, ForgeLM uses the model loaded at run start (the input model).

## Custom guards

You can register additional guards beyond the built-ins:

```yaml
evaluation:
  guards:
    custom_metric:
      function: "my_module.check_brand_voice"
      threshold: 0.7                    # function must return ≥ this
      severity: "critical"
```

```python
# my_module.py
def check_brand_voice(checkpoint_path: str) -> float:
    """Return a brand-voice score in [0, 1]."""
    # Run your custom eval...
    return 0.82
```

Custom guards integrate into the same revert flow.

## CI/CD integration

Auto-revert pairs naturally with CI exit codes:

```yaml
# .github/workflows/train.yml
- name: Train and evaluate
  run: forgelm --config configs/run.yaml
  # exit 0 = success, exit 3 = auto-revert triggered
```

CI failures from exit 3 are *expected* — they mean the gate caught a regression. Don't suppress them; investigate.

## Common pitfalls

:::warn
**Disabling auto-revert "to ship today".** Almost always the wrong call. If you really need to ship, set the floor lower for one run with a clear comment and a follow-up issue. The audit log will record the override.
:::

:::warn
**`last_good_checkpoint` pointing at a deleted path.** Auto-revert fails noisily if it can't find the restore target. Pin the last-good checkpoint at a stable path before kicking off training.
:::

:::tip
**Test auto-revert by sabotaging.** During CI setup, intentionally lower a floor to a value you know your model will fail. Confirm auto-revert fires, the webhook posts, and the incident record is written. Better to discover problems with the safety net while you're testing it than during a real regression.
:::

## See also

- [Benchmark Integration](#/evaluation/benchmarks) — defines floor thresholds.
- [Llama Guard Safety](#/evaluation/safety) — defines safety thresholds.
- [Webhooks](#/operations/webhooks) — notify on revert.
- [Audit Log](#/compliance/audit-log) — where revert events get recorded.
