---
title: Kahneman-Tversky Optimization (KTO)
description: Preference alignment from binary thumbs-up/down feedback, not paired comparisons.
---

# Kahneman-Tversky Optimization (KTO)

KTO trains a model on binary feedback — thumbs-up or thumbs-down on a single response — rather than paired chosen/rejected comparisons. Use it when your feedback collection produces single-response judgements, which is far more common in production than rigorous A/B preference data.

## When to use KTO

| Use KTO when... | Use DPO/SimPO when... |
|---|---|
| You have user thumbs-up/down on individual responses. | You have side-by-side `(chosen, rejected)` pairs. |
| Your annotation budget can't afford paired comparisons. | Your annotators rate pairs side-by-side. |
| Your feedback comes from production telemetry. | Feedback comes from labelling sessions. |

KTO's loss is built on prospect theory — the same psychology behind Kahneman-Tversky's original work. The model learns to maximise utility for desirable responses and minimise utility for undesirable ones, without ever seeing them paired.

## Quick example

```yaml
model:
  name_or_path: "./checkpoints/sft-base"
  max_length: 4096

data:
  dataset_name_or_path: "data/feedback.jsonl"

training:
  trainer_type: "kto"
  num_train_epochs: 1
  per_device_train_batch_size: 2
  learning_rate: 5.0e-7
  kto_beta: 0.1                  # flat field — KTO's only required tuning knob
  output_dir: "./checkpoints/kto"
```

The `desirable_weight` / `undesirable_weight` knobs from TRL's KTOConfig are not surfaced as ForgeLM config fields today; the trainer uses TRL's defaults (1.0 / 1.0) and operators who need asymmetric weighting wire it via a TRL-side override script. (Phase 28+ backlog.)

## Dataset format

```json
{"prompt": "How do I cancel?", "completion": "Just stop paying lol.", "label": false}
{"prompt": "How do I cancel?", "completion": "From Settings → Billing…", "label": true}
```

KTO needs both classes — at minimum 5-10% of your data should be the minority class. If your dataset is 99% thumbs-up and 1% thumbs-down (which is typical of production telemetry), KTO will struggle to find a useful signal in the rare class.

## Configuration parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `beta` | float | `0.1` | KL strength, same role as DPO. |
| `desirable_weight` | float | `1.0` | Up-weight thumbs-up rows in the loss. |
| `undesirable_weight` | float | `1.0` | Up-weight thumbs-down rows. |
| `loss_type` | string | `"sigmoid"` | `sigmoid` or `kto-pair` (paired-loss variant). |

:::tip
**Imbalanced data?** Set `undesirable_weight: 5.0` (or whatever ratio matches your imbalance) to amplify the rare-class signal. Don't oversample the JSONL itself — let the loss weights do it.
:::

## Compute and memory

About 1.5× SFT memory — keeps a reference model like DPO does, but processes single rows instead of paired ones.

## When KTO surprises people

KTO often *outperforms* DPO when applied to real-world thumbs-up/down telemetry, even when the same data could have been re-shaped into pairs. Two reasons:

1. Forced pairing creates spurious comparisons — a thumbs-up on one prompt and a thumbs-down on a different prompt aren't really "preferred vs dispreferred" of the same thing.
2. Production telemetry is imbalanced; KTO's per-class weights handle that more naturally.

## Common pitfalls

:::warn
**Treating `label: 1/0` as `true/false`.** Use the JSON booleans `true` and `false`, not integers. The data loader rejects integer labels for KTO.
:::

:::warn
**Single-class data.** If 100% of your rows are `label: true`, KTO has nothing to push against. The training will run but produce a near-identical model.
:::

## See also

- [DPO](#/training/dpo) — paired-preference cousin.
- [Dataset Formats](#/concepts/data-formats) — the `binary` format.
- [Choosing a Trainer](#/concepts/choosing-trainer) — decision tree.
