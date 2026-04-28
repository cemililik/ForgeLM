---
title: Benchmark Integration
description: Run lm-evaluation-harness tasks with per-task floor thresholds and auto-revert.
---

# Benchmark Integration

ForgeLM integrates with [lm-evaluation-harness](https://github.com/EleutherAI/lm-evaluation-harness) — the standard benchmark suite for LLMs — and adds the production layer on top: per-task floor thresholds, auto-revert on regression, and structured artifacts that flow into your compliance bundle.

## Quick example

```yaml
evaluation:
  benchmark:
    enabled: true
    tasks: ["hellaswag", "arc_easy", "truthfulqa", "mmlu"]
    floors:
      hellaswag: 0.55
      arc_easy: 0.70
      truthfulqa: 0.45
    num_fewshot: 0                      # zero-shot eval
    batch_size: 8
    output_dir: "./checkpoints/run/artifacts/"
```

After training, ForgeLM runs the listed tasks, compares to floors, and:
- All tasks pass floor → run succeeds (exit 0)
- Any task drops below floor → auto-revert to last-good checkpoint, exit 3

## Supported tasks

Anything in `lm-evaluation-harness` works. Common picks:

| Task | What it measures |
|---|---|
| `hellaswag` | Commonsense completion |
| `arc_easy`, `arc_challenge` | Grade-school science |
| `truthfulqa` | Resistance to common misconceptions |
| `mmlu` | Broad multitask knowledge |
| `winogrande` | Pronoun resolution |
| `gsm8k` | Grade-school math (chain of thought) |
| `humaneval` | Code completion |

For Turkish projects, ForgeLM ships templates for `mmlu_tr` and `belebele_tr` adapted to Turkish-specific tasks.

## Per-task floors

Floors define the minimum acceptable post-training score per task. The model isn't promoted until *every* task passes its floor.

```yaml
evaluation:
  benchmark:
    floors:
      hellaswag: 0.55
      mmlu: 0.50
      # tasks without floors are reported but don't block promotion
      truthfulqa: 0.45
```

A floor of `null` means "report but don't gate". A floor of `0` is the same as no floor (everything passes).

:::tip
Set floors slightly below your pre-training baseline. Goal: catch *regressions*, not require improvement on every task. A model that gains 5% on the target task while losing 2% on hellaswag is usually fine; one that drops 15% on hellaswag is broken.
:::

## Pre-train baselines

To know what floor to set, you need a pre-training baseline:

```shell
$ forgelm benchmark --model "Qwen/Qwen2.5-7B-Instruct" \
    --tasks hellaswag,arc_easy,truthfulqa,mmlu \
    --output baselines/qwen-2.5-7b.json
{"hellaswag": 0.61, "arc_easy": 0.75, "truthfulqa": 0.49, "mmlu": 0.52}
```

A reasonable floor is the baseline minus 0.03 (3% slack for stochastic variation):

```yaml
evaluation:
  benchmark:
    floors:
      hellaswag: 0.58                   # baseline 0.61 - 0.03
      arc_easy: 0.72
      truthfulqa: 0.46
      mmlu: 0.49
```

## Output artifacts

After eval, ForgeLM writes:

```text
checkpoints/run/artifacts/
├── benchmark_results.json             ← per-task scores + floor verdicts
└── benchmark_run.log                  ← full lm-eval-harness output
```

`benchmark_results.json` structure:

```json
{
  "tasks": {
    "hellaswag": {
      "score": 0.617, "floor": 0.55, "passed": true,
      "fewshot": 0, "n": 10042
    },
    "truthfulqa": {
      "score": 0.42, "floor": 0.45, "passed": false
    }
  },
  "verdict": "regression",
  "regressed_tasks": ["truthfulqa"]
}
```

CI pipelines parse `verdict`. See [Auto-Revert](#/evaluation/auto-revert) for the gating logic.

## Configuration parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `false` | Master switch. |
| `tasks` | list | `[]` | Task names from lm-eval-harness. |
| `floors` | dict | `{}` | Per-task minimum acceptable score. |
| `num_fewshot` | int | `0` | 0 for zero-shot, 5 for 5-shot. |
| `batch_size` | int | `8` | Eval batch size. |
| `limit` | int | `null` | Cap rows per task — for fast smoke tests. |
| `device` | string | `"cuda:0"` | Eval device. |

## Common pitfalls

:::warn
**Floors above pre-train baseline.** Set the floor higher than what the base model achieves and *every* run fails — auto-revert kicks in and you never get a checkpoint. Always start with `baseline - margin`.
:::

:::warn
**`num_fewshot` mismatch with reported public results.** Public leaderboards report at specific shot counts (e.g. MMLU is canonically 5-shot). Use the same setting if you want results to be comparable.
:::

:::tip
**Speed up iteration with `limit`.** Setting `limit: 100` runs 100 rows per task (instead of thousands) for ~10× faster eval. Use this in dev configs; remove for production.
:::

## See also

- [Auto-Revert](#/evaluation/auto-revert) — what happens when floors fail.
- [LLM-as-Judge](#/evaluation/judge) — qualitative eval beyond benchmarks.
- [Trend Tracking](#/evaluation/trend-tracking) — comparing scores across runs.
