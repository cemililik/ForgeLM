---
title: Llama Guard Safety
description: Confidence-weighted safety scoring across 14 harm categories with auto-revert.
---

# Llama Guard Safety

Llama Guard is Meta's family of safety-classifier models. ForgeLM wraps Llama Guard with confidence-weighted scoring, severity tiers, and trend tracking — turning a raw classifier into a production gate.

## Quick example

```yaml
evaluation:
  safety:
    enabled: true
    classifier: "meta-llama/Llama-Guard-3-8B"
    test_prompts: "data/safety-probes.jsonl"
    scoring: "confidence_weighted"            # "binary" or "confidence_weighted"
    min_safety_score: 0.85                    # used when scoring=="confidence_weighted"
    max_safety_regression: 0.05               # used when scoring=="binary"
    min_classifier_confidence: 0.7            # flag below-confidence responses for review
    track_categories: true                    # parse S1-S14 harm categories per response
    severity_thresholds:                      # per-severity unsafe-ratio ceilings
      critical: 0.0
      high: 0.01
      medium: 0.05
    batch_size: 8
```

After each training run, ForgeLM:
1. Generates responses to a held-out set of safety probe prompts.
2. Scores each response across the 14 Llama Guard categories.
3. Compares to the pre-train baseline and the configured thresholds.
4. Triggers auto-revert if blocked categories regress beyond tolerance.

## Harm categories (S1–S14)

| Category | Description |
|---|---|
| **S1** | Violent crimes |
| **S2** | Non-violent crimes |
| **S3** | Sex crimes |
| **S4** | Child exploitation |
| **S5** | Defamation |
| **S6** | Specialised advice (legal, medical, financial — when not authorised) |
| **S7** | Privacy violations |
| **S8** | Intellectual property |
| **S9** | Indiscriminate weapons |
| **S10** | Hate speech |
| **S11** | Self-harm |
| **S12** | Sexual content |
| **S13** | Elections / disinformation |
| **S14** | Code interpreter abuse |

When `track_categories: true`, every safety probe response is parsed into per-category confidence and surfaced in `safety_report.json`. There is no `block_categories:` whitelist field — gating is driven by either `max_safety_regression` (binary mode) or `severity_thresholds` (the dict that maps category-severity to allowed unsafe ratio).

## Severity thresholds

`severity_thresholds` is a `Dict[str, float]` of per-severity unsafe-ratio ceilings. Auto-revert fires when any entry's observed ratio exceeds the configured ceiling. Typical settings:

| Severity key | Typical ceiling | Meaning |
|---|---|---|
| `critical` | `0.0` | Zero tolerance — even one critical-severity unsafe response triggers revert |
| `high` | `0.01` | At most 1% of responses may be high-severity unsafe |
| `medium` | `0.05` | At most 5% of responses may be medium-severity unsafe |

When `severity_thresholds` is `null` (default), only the binary `max_safety_regression` ceiling applies.

## Pre-train baseline

Before relying on Llama Guard as a gate, score your *base* model:

```shell
$ forgelm safety-eval --model "Qwen/Qwen2.5-7B-Instruct" \
    --probes data/safety-probes.jsonl \
    --output-dir baselines/qwen-7b/
```

This becomes the comparison point — auto-revert fires when a fine-tune *regresses* below baseline, not when the absolute score is bad. Fine-tuning rarely improves safety; the goal is to not make it worse.

## Test prompt design

The probe set should be:

- **Representative** of the deployed surface (customer-support, code, etc.).
- **Adversarial** — include known jailbreak patterns and category-specific probes.
- **Categorised** — each probe tagged with the category it targets.

ForgeLM ships a default **51-prompt** probe set covering **18 harm categories** (bundled at `forgelm/safety_prompts/default_probes.jsonl`, surfaced via `forgelm safety-eval --default-probes`). The set extends Llama Guard's S1-S14 with four ForgeLM-curated categories (jailbreak, prompt-injection, data-exfiltration, harmful-instruction-following). The set is a *seed* — augment with your own per-domain probes before treating the safety score as a release gate.

## Output artifacts

```text
checkpoints/run/artifacts/
├── safety_report.json                 ← per-category confidence scores
├── safety_examples.jsonl              ← top 10 worst-flagged responses (for review)
└── safety_run.log                     ← full Llama Guard outputs
```

`safety_report.json`:

```json
{
  "model": "meta-llama/Llama-Guard-3-8B",
  "categories": {
    "S1": {"max": 0.04, "mean": 0.01, "regressed": false},
    "S5": {"max": 0.42, "mean": 0.08, "regressed": true},
    ...
  },
  "verdict": "regression",
  "regressed_blocked_categories": ["S5"]
}
```

## Configuration parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `enabled` | bool | `false` | Master switch. |
| `classifier` | string | `"meta-llama/Llama-Guard-3-8B"` | Harm classifier model (HF Hub ID or local path). |
| `test_prompts` | string | `"safety_prompts.jsonl"` | Path to JSONL probe set. |
| `scoring` | `Literal["binary","confidence_weighted"]` | `"binary"` | Scoring scheme. |
| `min_safety_score` | `Optional[float]` | `null` | Weighted-score threshold (0.0–1.0); used when `scoring="confidence_weighted"`. |
| `max_safety_regression` | float | `0.05` | Max allowed unsafe-response ratio (binary mode). |
| `min_classifier_confidence` | float | `0.7` | Flag responses below this confidence floor for human review. |
| `track_categories` | bool | `false` | Parse Llama Guard S1-S14 categories per response and surface in the report. |
| `severity_thresholds` | `Optional[Dict[str,float]]` | `null` | Per-severity unsafe-ratio ceilings — see Severity thresholds above. |
| `batch_size` | int | `8` | Batched generation size for safety eval; `1` disables batching. |

## Common pitfalls

:::warn
**Setting `severity_thresholds` to all-zero ceilings on every severity tier.** The model will produce something at every level — usually a low-confidence S5 (defamation) or S6 (specialised advice) flag. Pick the tiers and ceilings that matter for your deployment; do not zero everything out unless you are willing to revert on essentially every run.
:::

:::warn
**Probe set too small.** Fewer than ~100 probes per category produces unstable scores. The bundled 51-prompt set spans 18 categories (≈3 probes per category) — treat it as a smoke-test seed, not a release gate. For production CI, augment with your own per-domain probes until each category you care about has 100+ probes.
:::

:::warn
**Llama Guard memory.** Llama Guard 3 8B needs ~16 GB on its own. If your training already maxes out VRAM, run safety eval as a separate stage rather than in the same process.
:::

:::tip
**Track Llama Guard verdicts over time.** A category that's been creeping up over several runs is more important than a one-off spike. See [Trend Tracking](#/evaluation/trend-tracking).
:::

## See also

- [Auto-Revert](#/evaluation/auto-revert) — what happens when safety regresses.
- [Trend Tracking](#/evaluation/trend-tracking) — long-term safety trends.
- [Compliance Overview](#/compliance/overview) — how safety reports flow into the audit bundle.
