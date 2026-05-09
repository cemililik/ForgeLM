# Design: Interactive Configuration Wizard (`forgelm --wizard`)

> **Status: Implemented in v0.5.5; modernised Phase 22 / 2026-05-08;
> review-cycle 2 polish 2026-05-09 (`forgelm/wizard/` sub-package).**
> This document is retained as the historical design reference; the
> actual implementation in `forgelm/wizard/` (split from a 976-line
> monolith into five focused submodules) is now the source of truth.

> **Review-cycle 2 additions (2026-05-09):** validate-on-exit
> (`ForgeConfig.model_validate`), overwrite confirmation with auto-
> suffix, non-tty stdin refusal, pre-flight checklist, atomic
> `wizard_state.yaml` writes (`tempfile` + `os.replace`), webhook
> SSRF preflight, CLI ↔ web safety field union, web wizard
> `model.max_length` surface, monitoring `endpoint_env` syntax,
> cross-tab `storage` sync, distinct `EXIT_WIZARD_CANCELLED = 5`
> exit code, best-effort `readline` integration. Schema-default
> parity tightened: judge `min_score` `5.0` (was `6.5`), web
> `learningRate` `2e-5` (was `1e-4`), web `batchSize` `4` (was `2`).

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

## Implemented flow (`forgelm/wizard::run_wizard`)

The shipped wizard (Phase 22 / 2026-05-08 modernisation) runs **9 steps**
plus an optional quickstart-template prelude (`_maybe_run_quickstart_template`).
Step ordering and naming are kept in lockstep with the in-browser web
wizard at `site/js/wizard.js`:

0. **Quickstart prelude** *(optional)*: offer the curated
   `forgelm/quickstart.py::TEMPLATES` list (`customer-support`,
   `code-assistant`, `domain-expert`, `medical-qa-tr`, `grpo-math`)
   as a one-shot shortcut.  When accepted, the prelude generates the
   config from the bundled template and skips the full 9-step flow.
1. **Welcome**: experience toggle (beginner / expert), navigation
   primer (`back` / `reset` / Ctrl-C), hardware detection (torch +
   CUDA + VRAM), backend hint (`unsloth` on Linux + GPU, otherwise
   `transformers`).
2. **Use-case**: same registry as the prelude, surfaced inside the
   full flow so operators who declined the shortcut still benefit
   from sensible preselects (the choice seeds Steps 3 + 5 defaults
   but the operator can still override every later answer).
3. **Model**: pick a HuggingFace Hub ID from `POPULAR_MODELS` (kept
   in lockstep with `site/js/wizard.js`'s presets) or enter a custom
   path.
4. **Strategy**: 6 cards (QLoRA / LoRA / DoRA / PiSSA / rsLoRA /
   GaLore) covering the full `LoraConfigModel.method` Literal +
   GaLore as a separate axis.  Captures `lora.r`, `lora.alpha`,
   `lora.target_modules` (standard / extended / full preset).
5. **Trainer + per-trainer hyperparameters**: pick `trainer_type` from
   `{sft, dpo, simpo, kto, orpo, grpo}`; the wizard then prompts for
   the trainer's specific knobs (`dpo_beta`, `simpo_beta` /
   `simpo_gamma`, `kto_beta`, `orpo_beta`, `grpo_num_generations`,
   `grpo_max_completion_length`, `grpo_reward_model`).  SFT short-
   circuits (no per-trainer knobs to surface).
6. **Dataset**: HF Hub ID, local JSONL, or directory of raw documents.
   Directory inputs trigger inline ingestion (Phase 11.5).  JSONL
   inputs trigger an inline audit (Phase 12.5).  Optional Article 10
   `data.governance` accordion.
7. **Training parameters**: epochs, batch size, max length, output
   directory, RoPE scaling (4 schema types incl. `longrope`),
   NEFTune, OOM recovery, GaLore advanced (6-variant optimizer +
   rank).
8. **Compliance + risk**: `compliance` (Article 11 + Annex IV §1)
   plus optional `risk_assessment` (Article 9), `data.governance`
   (Article 10), `retention` (GDPR Article 5(1)(e) + 17),
   `monitoring` (Article 12 + 17) accordions.  This step is
   deliberately collected **before** evaluation so the wizard can
   front-stop the F-compliance-110 strict-tier gate.
9. **Operations + evaluation**: `evaluation.auto_revert`,
   `evaluation.safety` (Llama Guard, probe set resolved through
   `importlib.resources`), `evaluation.benchmark`,
   `evaluation.llm_judge`, `webhook` (single prompt with `env:VAR`
   prefix sugar), `synthetic` block.  After the operator answers,
   `_apply_strict_tier_coercion` enforces F-compliance-110 (high-
   risk → safety enabled + Article 14 staging gate).

Persistence: state snapshot is written to
`$XDG_CACHE_HOME/forgelm/wizard_state.yaml` after each completed step
so a Ctrl-C / fresh session can offer to resume.  Snapshot is cleared
on successful completion or when the operator types `reset` / `r`.

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
