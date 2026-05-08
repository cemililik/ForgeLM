# Design: Interactive Configuration Wizard (`forgelm --wizard`)

> **Status: Implemented in v0.5.5.** This document is retained as the
> historical design reference; the actual implementation in
> `forgelm/wizard.py` (≈800 lines) diverged from the original 6-step
> sketch in three concrete ways and is now the source of truth.

## Overview

To improve accessibility for users coming from no-code tools (like the
DGX-Spark Finetuner), ForgeLM ships an interactive wizard mode that
asks operator-level questions and writes a validated `config.yaml`.

The wizard is invoked as:

```shell
forgelm --wizard
```

(The original `python3 -m forgelm.cli --wizard` form is preserved; the
top-level `forgelm --wizard` flag is the canonical operator-facing
entry point.)

## Implemented flow (`forgelm/wizard.py:799+`)

The shipped wizard runs **8 steps** plus an optional template prelude
(`_maybe_run_quickstart_template`):

0.  **Quickstart prelude** *(optional)*: detect whether the operator
    is starting from a bundled `forgelm/templates/<name>/config.yaml`
    template (e.g. `customer-support`, `medical-qa-tr`) and, if so,
    pre-fill the rest of the wizard's defaults from that template.
1.  **Welcome & Hardware Detection**: detect available VRAM via
    `forgelm.fit_check`; suggest a backend (`transformers` vs
    `unsloth`).
2.  **Model Selection**: prompt for a HuggingFace repository name;
    pre-flight check for `safetensors` shards via the HF Hub API.
3.  **Strategy Selection**: LoRA / QLoRA / DoRA / PiSSA / rsLoRA
    selection with simplified explanations.
4.  **Dataset Path**: prompt for a local file path or HF Hub dataset
    id; validate format auto-detection (SFT / DPO / KTO / GRPO) on
    the fly via `forgelm.data._detect_dataset_format`.
5.  **Trainer + Hyperparameters**: select `trainer_type` from
    `{sft, dpo, simpo, kto, orpo, grpo}` and the hyperparameters most
    operators tune (`learning_rate`, `num_train_epochs`,
    `per_device_train_batch_size`, `gradient_accumulation_steps`).
6.  **Compliance + Safety**: prompt for `compliance.risk_classification`,
    `evaluation.require_human_approval`, and the safety classifier
    block (`safety.enabled`, `safety.classifier`).
7.  **Output Config**: ask for a filename to save the generated YAML.
8.  **Quick Run**: ask whether to start training immediately using the
    generated config; if yes, dispatches to the standard training
    pipeline.

## Implementation Details

The wizard uses **pure stdlib** `input()` prompts — neither `rich` nor
`questionary` was adopted. The rationale:

- The wizard runs inside CI containers and minimal-image deployments
  where adding a TUI dependency for a one-shot interactive flow is
  costly.
- Pure-stdlib prompts keep the dependency footprint identical to the
  rest of `forgelm` (only `pyyaml` + `pydantic`).
- The output is plain YAML; the visual polish of `questionary`-style
  picklist UIs gave no benefit at the schema-validation step that
  follows.

The wizard's primary output is a standard `config.yaml` validated
against `ForgeConfig` before being written, ensuring compatibility
with the existing config-driven architecture. Any operator response
that fails Pydantic validation is re-prompted with the validation
error message inline.
