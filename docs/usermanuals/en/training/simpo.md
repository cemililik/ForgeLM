---
title: Simple Preference Optimization (SimPO)
description: Reference-free preference learning — DPO without keeping a reference model in memory.
---

# Simple Preference Optimization (SimPO)

SimPO is a streamlined cousin of DPO that removes the reference model from the equation. The trade-off: roughly half the VRAM, slightly less stability.

## When to use SimPO

| Use SimPO when... | Use DPO instead when... |
|---|---|
| Your VRAM budget is tight (e.g. 13B+ on a single 24 GB GPU). | You can afford the second model in memory. |
| You don't have a clean reference checkpoint. | Your SFT checkpoint is high quality and trustworthy. |
| You want simpler training dynamics. | Stability and reproducibility matter more than VRAM. |

:::tip
A practical rule: if [`--fit-check`](#/operations/vram-fit-check) reports `OOM` for DPO, switch to SimPO before considering smaller models or shorter contexts. The quality gap is usually less than 5% on standard benchmarks.
:::

## Quick example

```yaml
model:
  name_or_path: "./checkpoints/sft-base"
  max_length: 4096

data:
  dataset_name_or_path: "data/preferences.jsonl"

training:
  trainer_type: "simpo"
  num_train_epochs: 1
  per_device_train_batch_size: 2
  learning_rate: 8.0e-7      # ~10× smaller than DPO
  simpo_beta: 2.0            # higher than DPO's 0.1 — flat field
  simpo_gamma: 1.0           # margin term — flat field
  output_dir: "./checkpoints/simpo"
```

## Dataset format

Same as DPO — `preference` format with `prompt`, `chosen`, `rejected`. See [Dataset Formats](#/concepts/data-formats).

## Configuration parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `beta` | float | `2.0` | Length-normalised reward scale. Higher = stronger preference shift. SimPO's beta is *not* the same scale as DPO's. |
| `gamma` | float | `1.0` | Margin term — the gap SimPO tries to maintain between chosen and rejected log-likelihoods. |
| `loss_type` | string | `"sigmoid"` | `sigmoid` or `hinge`. |
| `length_normalize` | bool | `true` | Normalise log-probs by sequence length. SimPO's signature feature. |
| `label_smoothing` | float | `0.0` | Smoothing on preference labels for noisy data. |

## Compute and memory

| Model | LoRA rank | `max_length` | Approx VRAM (QLoRA 4-bit) |
|---|---|---|---|
| 7B | 16 | 4096 | 9 GB |
| 13B | 16 | 4096 | 16 GB |
| 8B | 32 | 8192 | 18 GB |

About 1.2× SFT memory — much lighter than DPO's 2×.

## Choosing `beta` and `gamma`

| Combination | Behaviour |
|---|---|
| `beta=2.0`, `gamma=1.0` | Default. Balanced. |
| `beta=2.5`, `gamma=1.4` | More aggressive preference shift. |
| `beta=1.5`, `gamma=0.5` | Gentler, closer to original SFT outputs. |

:::warn
SimPO's `beta` is on a different scale than DPO's `beta`. Don't copy DPO hyperparameters as-is — start from SimPO defaults.
:::

## Common pitfalls

:::warn
**Overshooting on beta.** SimPO is more sensitive than DPO; high `beta` plus a small dataset produces a model that aggressively prefers chosen but loses general capability. Watch your benchmark scores during training.
:::

:::warn
**Using SimPO without SFT first.** Same warning as DPO — start from a quality SFT checkpoint, not a raw base model.
:::

## See also

- [DPO](#/training/dpo) — the reference-based cousin; switch to SimPO when VRAM is tight.
- [ORPO](#/training/orpo) — combines SFT and preference loss in one stage.
- [Configuration Reference](#/reference/configuration) — full parameter list.
