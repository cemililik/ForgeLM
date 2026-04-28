---
title: LLM-as-Judge
description: Quality scoring with OpenAI or a local judge model — pairwise, single-rubric, or ELO-style.
---

# LLM-as-Judge

Standard benchmarks measure narrow capabilities; they don't capture "is this response actually good?". LLM-as-judge fills that gap by using a stronger model to evaluate yours. ForgeLM supports three modes: pairwise comparison, single-rubric scoring, and ELO-style ranking.

## When to use

| Use LLM-as-judge when... | Use benchmarks when... |
|---|---|
| Output quality is subjective (helpful, polite, on-brand). | The task has a verifiable answer. |
| You don't have ground truth. | You have ground truth. |
| You're comparing two models' qualitative output. | You're tracking absolute performance over time. |
| Cost is acceptable (~$1-5 per 1K judgements with GPT-4o). | You need free, local eval. |

## Quick example

```yaml
evaluation:
  judge:
    enabled: true
    mode: "pairwise"                    # or single-rubric, elo
    judge_model:
      provider: "openai"
      model: "gpt-4o-mini"               # cheaper than gpt-4o, almost as good for judging
      api_key: "${OPENAI_API_KEY}"
    baseline_model: "./checkpoints/sft-base"
    test_prompts: "data/eval-prompts.jsonl"
    num_samples: 200
    rubric: "default"                   # or path to custom rubric
```

## Pairwise mode

Asks the judge: "Response A or Response B — which is better, and why?" Aggregates win-rates.

```json
{
  "pairwise_results": {
    "wins": 124,
    "losses": 56,
    "ties": 20,
    "win_rate": 0.62,
    "judge_explanations_sample": [...]
  }
}
```

A win rate above 0.55 with 200+ samples is statistically meaningful. Below that, run more samples or accept that the differences are noise.

## Single-rubric mode

Asks the judge to score each response on a rubric (1-5 stars per criterion).

```yaml
evaluation:
  judge:
    mode: "single-rubric"
    rubric:
      criteria:
        - name: "helpfulness"
          description: "Does the response solve the user's problem?"
          scale: 5
        - name: "tone"
          description: "Is the tone appropriate for customer support?"
          scale: 5
        - name: "factual_accuracy"
          description: "Are claims correct?"
          scale: 5
```

Output:

```json
{
  "rubric_means": {
    "helpfulness": 4.2,
    "tone": 4.7,
    "factual_accuracy": 3.8
  },
  "rubric_distributions": {...}
}
```

## ELO mode

Runs round-robin pairwise comparisons across multiple model versions, computes ELO ratings.

```yaml
evaluation:
  judge:
    mode: "elo"
    candidates:
      - name: "v1"
        path: "./checkpoints/v1"
      - name: "v2"
        path: "./checkpoints/v2"
      - name: "v3-current"
        path: "./checkpoints/v3"
    rounds: 50
```

Output: ELO ratings per candidate. Useful when comparing across many runs (e.g. hyperparameter sweep).

## Judge model choice

| Judge | Cost / 1K judgements | Quality |
|---|---|---|
| `openai:gpt-4o` | ~$5 | Highest. Default for production. |
| `openai:gpt-4o-mini` | ~$1 | 90% of gpt-4o quality. Recommended. |
| `anthropic:claude-haiku-4` | ~$1.50 | Comparable to gpt-4o-mini. |
| `local:Qwen2.5-72B-Instruct` | $0 (your GPU time) | Reasonable; weaker on subtle judgement calls. |
| `local:Llama-3.1-70B-Instruct` | $0 | Slightly worse than Qwen 72B for judging. |

## Reducing variance

Single judge runs are noisy. ForgeLM ships standard variance-reduction:

- **Self-consistency** — `--num-judgements 3` runs each comparison three times, takes majority.
- **Position swap** — alternates which response is "A" vs "B" to detect position bias.
- **Multiple rubrics** — averages across criteria.

```yaml
evaluation:
  judge:
    self_consistency: 3                 # 3 votes per comparison
    swap_positions: true                # detect position bias
```

## Cost controls

```yaml
evaluation:
  judge:
    budget_usd: 20.0                    # halt at $20
    rate_limit:
      requests_per_minute: 60
```

When the budget is hit, judge halts with partial results.

## Common pitfalls

:::warn
**Using the same model as judge and student.** A 7B model judging another 7B's outputs won't catch subtle quality issues. Use a stronger judge.
:::

:::warn
**Position bias.** Judges often prefer the first response slightly. Always set `swap_positions: true` for pairwise comparisons.
:::

:::warn
**Tiny sample sizes.** Comparing two models with 20 prompts is statistical noise. Use 200+ for meaningful win-rates.
:::

:::tip
**Pair judge with benchmarks.** A model that wins on judge but regresses on benchmarks is overfitting to whatever the judge prefers. Both signals matter.
:::

## See also

- [Benchmark Integration](#/evaluation/benchmarks) — quantitative eval companion.
- [Synthetic Data](#/data/synthetic-data) — same provider abstraction.
- [Auto-Revert](#/evaluation/auto-revert) — judge can be a gating signal.
