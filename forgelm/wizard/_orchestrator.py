"""Step machine + public entry point for the wizard.

The orchestrator threads a single :class:`_WizardState` through every
step, persists after each step, and supports back-step / reset.
Each step is registered as a small :class:`_StepDef`.  Steps return
``None`` (success), raise :class:`WizardBack` (operator typed
``back``), or raise :class:`WizardReset` (operator typed ``reset``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from ._byod import (
    _finalize_quickstart_path,
    _maybe_run_quickstart_template,
    _prompt_dataset_path_with_ingest_offer,
)
from ._collectors import (
    _PREFERENCE_COLUMNS_HINT,
    _STRICT_RISK_TIERS,
    _collect_benchmark,
    _collect_compliance_metadata,
    _collect_data_governance,
    _collect_galore_config,
    _collect_judge,
    _collect_monitoring,
    _collect_neftune_alpha,
    _collect_retention,
    _collect_risk_assessment,
    _collect_rope_scaling,
    _collect_safety_config,
    _collect_synthetic,
    _collect_trainer_hyperparameters,
    _collect_webhook_config,
    _default_safety_probes_path,
    _select_strategy,
    _select_use_case,
)
from ._io import (
    _PLATFORM,
    WizardBack,
    WizardReset,
    _detect_hardware,
    _print,
    _prompt,
    _prompt_int,
    _prompt_required,
    _prompt_yes_no,
)
from ._state import (
    _MANUAL_USE_CASE,
    DEFAULT_BATCH_SIZE,
    DEFAULT_DROPOUT,
    DEFAULT_EPOCHS,
    DEFAULT_LORA_R,
    DEFAULT_LR,
    DEFAULT_MAX_LENGTH,
    POPULAR_MODELS,
    TARGET_MODULE_PRESETS,
    _clear_wizard_state,
    _load_wizard_state,
    _print_step_diff,
    _print_wizard_summary,
    _save_config_to_file,
    _save_wizard_state,
    _strip_internal_meta,
    _wizard_state_path,
    _WizardState,
)

# ---------------------------------------------------------------------------
# Strict-tier auto-coercion — Phase 22 / G8.  ``ForgeConfig`` raises
# ``ConfigError`` at load time when ``risk_classification ∈
# {high-risk, unacceptable}`` and ``evaluation.safety.enabled =
# False``; the wizard front-stops the same gate.
# ---------------------------------------------------------------------------


def _apply_strict_tier_coercion(config: Dict[str, Any], compliance: Dict[str, Any]) -> None:
    """Mutate *config* in place to satisfy F-compliance-110 strict-tier requirements."""
    if compliance.get("risk_classification") not in _STRICT_RISK_TIERS:
        return
    _print(
        "\n  Risk classification is high-risk / unacceptable — Article 9 "
        "(F-compliance-110) requires safety evaluation enabled and Article 14 "
        "requires the human-approval staging gate.  Auto-enabling both."
    )
    evaluation = config.setdefault("evaluation", {})
    evaluation.setdefault("auto_revert", True)
    evaluation["require_human_approval"] = True
    safety = evaluation.get("safety")
    if not isinstance(safety, dict) or not safety.get("enabled"):
        evaluation["safety"] = {
            "enabled": True,
            "test_prompts": _default_safety_probes_path(),
            "scoring": "binary",
            "track_categories": True,
            "severity_thresholds": {"critical": 0, "high": 0.01, "medium": 0.05},
        }


# ---------------------------------------------------------------------------
# Beginner / expert tutorial-paragraph helpers
# ---------------------------------------------------------------------------


def _is_beginner(state: _WizardState) -> bool:
    return state.experience == "beginner"


def _print_tutorial(state: _WizardState, lines: List[str]) -> None:
    """Print a 2-3-line tutorial paragraph in beginner mode; skip in expert mode."""
    if not _is_beginner(state):
        return
    _print()
    for line in lines:
        _print(f"  · {line}")


# ---------------------------------------------------------------------------
# Step definitions
# ---------------------------------------------------------------------------


@dataclass
class _StepDef:
    """A single step in the full-wizard flow."""

    label: str
    runner: Callable[[_WizardState], None]


def _step_welcome(state: _WizardState) -> None:
    """Step 1: welcome + experience toggle + hardware detection."""
    _print("\n[1/9] Welcome")
    _print(
        "\n  ForgeLM walks you through producing a validated `config.yaml`.  "
        "Type `back` / `b` at any prompt to return to the previous step, "
        "`reset` / `r` to clear answers, `cancel` / `q` to exit cleanly."
    )
    if _prompt_yes_no(
        "First-time user?  (beginner mode prefixes each step with a short tutorial paragraph)",
        default=False,
    ):
        state.experience = "beginner"
    else:
        state.experience = "expert"
    hw = _detect_hardware()
    if hw["gpu_available"]:
        _print(f"  GPU detected: {hw['gpu_name']} ({hw['vram_gb']} GB VRAM, CUDA {hw['cuda_version']})")
    else:
        _print("  No GPU detected. Training will use CPU (very slow for real workloads).")
    suggested_backend = "transformers"
    if hw["gpu_available"] and _PLATFORM == "linux":
        suggested_backend = "unsloth"
        _print("  Recommended backend: unsloth (Linux + GPU detected)")
    elif hw["gpu_available"]:
        _print("  Recommended backend: transformers (Unsloth requires Linux)")
    state.config.setdefault("model", {})["backend"] = suggested_backend


def _step_use_case(state: _WizardState) -> None:
    """Step 2: use-case preselect."""
    _print("\n[2/9] Use-case")
    _print_tutorial(
        state,
        [
            "A use-case picks sensible defaults for trainer + model + dataset.",
            "Pick `custom` to fill every field manually.",
            "Whatever you pick, you can still override every later step.",
        ],
    )
    use_case_key, preset = _select_use_case()
    state.use_case = use_case_key
    if preset.get("model"):
        state.config.setdefault("model", {})["name_or_path"] = preset["model"]
    if preset.get("trainer_type"):
        state.config.setdefault("training", {})["trainer_type"] = preset["trainer_type"]


def _step_model(state: _WizardState) -> None:
    """Step 3: model selection."""
    _print("\n[3/9] Model Selection")
    _print_tutorial(
        state,
        [
            "Pick the base model your fine-tune will adapt.",
            "Smaller models train faster but cap your reasoning ceiling.",
            "QLoRA on a 7B model fits comfortably in 12 GB VRAM.",
        ],
    )
    preset_default = state.config.get("model", {}).get("name_or_path")
    options = list(POPULAR_MODELS)
    options.append("Custom (enter your own)")
    if preset_default and preset_default in POPULAR_MODELS:
        default_idx = POPULAR_MODELS.index(preset_default) + 1
    else:
        default_idx = 1
    from ._io import _prompt_choice

    chosen = _prompt_choice("Choose a model:", options, default=default_idx)
    if chosen.startswith("Custom"):
        model_name = _prompt_required("HuggingFace model name or local path")
    else:
        model_name = chosen
    state.config.setdefault("model", {})["name_or_path"] = model_name


def _step_strategy(state: _WizardState) -> None:
    """Step 4: strategy + LoRA params."""
    _print("\n[4/9] Fine-Tuning Strategy")
    _print_tutorial(
        state,
        [
            "QLoRA is the safest default: 4-bit base + low-rank adapter.",
            "DoRA / PiSSA / rsLoRA tweak the adapter for better convergence.",
            "GaLore replaces adapters with full-parameter training via gradient projection.",
        ],
    )
    strategy = _select_strategy()
    from ._io import _prompt_choice

    target_preset = _prompt_choice(
        "Target modules:",
        ["standard (q_proj, v_proj)", "extended (q, k, v, o)", "full (all linear layers)"],
        default=1,
    )
    preset_key = target_preset.split(" ")[0]
    target_modules = TARGET_MODULE_PRESETS.get(preset_key, TARGET_MODULE_PRESETS["standard"])
    lora_r = _prompt_int("LoRA rank (r)", DEFAULT_LORA_R, min_val=1, max_val=512)
    lora_alpha = _prompt_int("LoRA alpha", lora_r * 2, min_val=1, max_val=1024)
    state.config.setdefault("model", {})["load_in_4bit"] = strategy.load_in_4bit
    state.config["model"].setdefault("trust_remote_code", False)
    lora_block = state.config.setdefault("lora", {})
    lora_block["r"] = lora_r
    lora_block["alpha"] = lora_alpha
    lora_block["dropout"] = DEFAULT_DROPOUT
    lora_block["bias"] = "none"
    lora_block["method"] = strategy.method
    lora_block["target_modules"] = target_modules
    lora_block["task_type"] = "CAUSAL_LM"
    state.config.setdefault("training", {})["galore_enabled"] = strategy.use_galore
    state.config.setdefault("_wizard_meta", {})["use_galore"] = strategy.use_galore


def _step_trainer(state: _WizardState) -> None:
    """Step 5: trainer + per-trainer hyperparameters."""
    _print("\n[5/9] Training Objective")
    _print_tutorial(
        state,
        [
            "SFT is supervised fine-tuning — the standard instruction-tuning recipe.",
            "DPO / SimPO / KTO / ORPO align via preferences (chosen vs rejected).",
            "GRPO is reasoning RL (DeepSeek-R1 style); needs a reward signal.",
        ],
    )
    objectives = [
        "sft — Supervised Fine-Tuning (standard instruction tuning)",
        "dpo — Direct Preference Optimization (chosen/rejected pairs)",
        "simpo — Simple Preference Optimization (no reference model, lower memory)",
        "kto — Binary feedback alignment (thumbs up/down, practical for production)",
        "orpo — Odds Ratio Preference Optimization (SFT + alignment in one stage)",
        "grpo — Group Relative Policy Optimization (reasoning RL, like DeepSeek-R1)",
    ]
    preset = state.config.get("training", {}).get("trainer_type", "sft")
    default_idx = next(
        (i for i, opt in enumerate(objectives, 1) if opt.startswith(f"{preset} —")),
        1,
    )
    from ._io import _prompt_choice

    chosen = _prompt_choice("Choose your training objective:", objectives, default=default_idx)
    trainer_type = chosen.split(" — ")[0].strip().lower()
    dataset_format_hint = {
        "sft": "Columns: System (opt), User/instruction, Assistant/output — or 'messages' list",
        "dpo": _PREFERENCE_COLUMNS_HINT,
        "simpo": _PREFERENCE_COLUMNS_HINT,
        "orpo": _PREFERENCE_COLUMNS_HINT,
        "kto": "Columns: prompt, completion, label (boolean: true=good, false=bad)",
        "grpo": "Columns: prompt (model generates responses during training)",
    }.get(trainer_type, "Standard format")
    _print(f"  Dataset format: {dataset_format_hint}")
    training_block = state.config.setdefault("training", {})
    training_block["trainer_type"] = trainer_type
    hyperparams = _collect_trainer_hyperparameters(trainer_type)
    training_block.update(hyperparams)


def _step_dataset(state: _WizardState) -> None:
    """Step 6: dataset path + optional Article 10 governance."""
    _print("\n[6/9] Dataset")
    _print_tutorial(
        state,
        [
            "Point the wizard at an HF Hub dataset ID, a local JSONL, or a directory of raw documents.",
            "Directories of raw documents trigger inline ingestion (PDF / DOCX / EPUB / TXT / MD).",
            "JSONL files are auto-audited (length / language / dedup / PII / secrets).",
        ],
    )
    dataset_path = _prompt_dataset_path_with_ingest_offer(
        "HuggingFace dataset name or local file path (or directory of raw documents)",
    )
    data_block = state.config.setdefault("data", {})
    data_block["dataset_name_or_path"] = dataset_path
    data_block.setdefault("shuffle", True)
    data_block.setdefault("clean_text", True)
    data_block.setdefault("add_eos", True)
    governance = _collect_data_governance(mandatory=False)
    if governance:
        data_block["governance"] = governance


def _step_training_params(state: _WizardState) -> None:
    """Step 7: epochs + batch + max_length + RoPE + NEFTune + OOM + GaLore advanced."""
    _print("\n[7/9] Training Parameters")
    _print_tutorial(
        state,
        [
            "Epochs / batch / learning_rate are the three knobs you'll tune most often.",
            "Long-context (>4096) automatically prompts for RoPE scaling.",
            "OOM recovery halves the batch size on CUDA out-of-memory and retries.",
        ],
    )
    epochs = _prompt_int("Number of epochs", DEFAULT_EPOCHS, min_val=1, max_val=1000)
    batch_size = _prompt_int("Batch size per device", DEFAULT_BATCH_SIZE, min_val=1, max_val=512)
    max_length = _prompt_int("Max sequence length", DEFAULT_MAX_LENGTH, min_val=64, max_val=131072)
    output_dir = _prompt("Output directory", "./checkpoints")
    rope_scaling = _collect_rope_scaling(max_length)
    neftune_alpha = _collect_neftune_alpha()
    use_oom_recovery = _prompt_yes_no(
        "Enable OOM recovery? (auto-halves batch size on CUDA out-of-memory, then retries)",
        default=False,
    )
    use_galore = bool(state.config.get("_wizard_meta", {}).get("use_galore"))
    galore_config = _collect_galore_config(use_galore)
    model_block = state.config.setdefault("model", {})
    model_block["max_length"] = max_length
    training_block = state.config.setdefault("training", {})
    training_block["output_dir"] = output_dir
    training_block.setdefault("final_model_dir", "final_model")
    training_block.setdefault("merge_adapters", False)
    training_block["num_train_epochs"] = epochs
    training_block["per_device_train_batch_size"] = batch_size
    training_block.setdefault("gradient_accumulation_steps", 2)
    training_block.setdefault("learning_rate", DEFAULT_LR)
    training_block.setdefault("warmup_ratio", 0.1)
    training_block.setdefault("weight_decay", 0.01)
    training_block.setdefault("eval_steps", 200)
    training_block.setdefault("save_steps", 200)
    training_block.setdefault("save_total_limit", 3)
    training_block.setdefault("packing", False)
    training_block.update(galore_config)
    if neftune_alpha is not None:
        training_block["neftune_noise_alpha"] = neftune_alpha
    if rope_scaling is not None:
        training_block["rope_scaling"] = rope_scaling
    if use_oom_recovery:
        training_block["oom_recovery"] = True
        training_block["oom_recovery_min_batch_size"] = 1


def _step_compliance(state: _WizardState) -> None:
    """Step 8: compliance / risk_classification / risk_assessment / governance / retention / monitoring."""
    _print("\n[8/9] Compliance + risk")
    _print_tutorial(
        state,
        [
            "Configure EU AI Act compliance metadata for Annex IV documentation.",
            "high-risk / unacceptable risk_classification triggers Article 9 / 14 auto-coercion.",
            "Article 10 data.governance and retention horizons are optional unless you're high-risk.",
        ],
    )
    if not _prompt_yes_no(
        "Configure EU AI Act compliance metadata?",
        default=False,
    ):
        return
    compliance = _collect_compliance_metadata()
    state.config["compliance"] = compliance
    risk = compliance.get("risk_classification", "minimal-risk")
    risk_assessment = _collect_risk_assessment(risk)
    if risk_assessment:
        state.config["risk_assessment"] = risk_assessment
    is_strict = risk in _STRICT_RISK_TIERS
    governance = _collect_data_governance(mandatory=is_strict)
    if governance:
        state.config.setdefault("data", {})["governance"] = governance
    retention = _collect_retention()
    if retention:
        state.config["retention"] = retention
    monitoring = _collect_monitoring()
    if monitoring:
        state.config["monitoring"] = monitoring


def _step_evaluation(state: _WizardState) -> None:
    """Step 9 (operations): evaluation gates, webhooks, synthetic, save."""
    _print("\n[9/9] Operations + evaluation")
    _print_tutorial(
        state,
        [
            "Evaluation gates (auto_revert + safety + benchmark + judge) protect against regressions.",
            "Webhooks notify Slack / Teams / your CI when training starts, succeeds, or fails.",
            "Synthetic-data lets a stronger teacher model generate extra training examples.",
        ],
    )
    evaluation: Dict[str, Any] = {}
    if _prompt_yes_no("Enable auto-revert (discard model if quality drops)?", default=False):
        evaluation["auto_revert"] = True
        max_loss = _prompt("Max acceptable loss (leave empty for baseline-only)", "")
        if max_loss.strip():
            try:
                evaluation["max_acceptable_loss"] = float(max_loss)
            except ValueError:
                _print(f"  '{max_loss}' is not a number; max_acceptable_loss left unset.")
    risk = state.config.get("compliance", {}).get("risk_classification", "minimal-risk")
    safety = _collect_safety_config(default_enabled=risk in _STRICT_RISK_TIERS)
    if safety:
        evaluation["safety"] = safety
    benchmark = _collect_benchmark()
    if benchmark:
        evaluation["benchmark"] = benchmark
    judge = _collect_judge()
    if judge:
        evaluation["llm_judge"] = judge
    if evaluation:
        state.config["evaluation"] = evaluation
    webhook_section = _collect_webhook_config()
    if webhook_section:
        state.config["webhook"] = webhook_section
    synthetic = _collect_synthetic()
    if synthetic:
        state.config["synthetic"] = synthetic
    compliance = state.config.get("compliance")
    if compliance:
        _apply_strict_tier_coercion(state.config, compliance)


_STEPS: Tuple[_StepDef, ...] = (
    _StepDef("welcome", _step_welcome),
    _StepDef("use-case", _step_use_case),
    _StepDef("model", _step_model),
    _StepDef("strategy", _step_strategy),
    _StepDef("trainer", _step_trainer),
    _StepDef("dataset", _step_dataset),
    _StepDef("training-params", _step_training_params),
    _StepDef("compliance", _step_compliance),
    _StepDef("evaluation", _step_evaluation),
)


# ---------------------------------------------------------------------------
# Resume + step-machine driver
# ---------------------------------------------------------------------------


def _maybe_resume_state() -> _WizardState:
    """Offer to resume an in-progress wizard run."""
    snapshot = _load_wizard_state()
    if snapshot is None:
        return _WizardState()
    completed = snapshot.get("completed_steps", [])
    if not completed:
        return _WizardState()
    if not _prompt_yes_no(
        f"Resume previous wizard run? (completed {len(completed)} step(s): {', '.join(completed)})",
        default=True,
    ):
        _clear_wizard_state()
        return _WizardState()
    return _WizardState(
        experience=snapshot.get("experience", "expert"),
        use_case=snapshot.get("use_case", _MANUAL_USE_CASE),
        current_step=snapshot.get("current_step", 0),
        completed_steps=list(completed),
        config=dict(snapshot.get("config", {})),
    )


def _persist_state(state: _WizardState) -> None:
    """Snapshot the wizard's in-memory state to disk."""
    _save_wizard_state(
        {
            "experience": state.experience,
            "use_case": state.use_case,
            "current_step": state.current_step,
            "completed_steps": state.completed_steps,
            "config": state.config,
        }
    )


def _drive_wizard_steps(state: _WizardState) -> _WizardState:
    """Run the wizard's step machine, honouring back / reset."""
    while state.current_step < len(_STEPS):
        step = _STEPS[state.current_step]
        prev_config = json.loads(json.dumps(state.config))  # deep copy
        try:
            step.runner(state)
        except WizardBack:
            if state.current_step == 0:
                _print("  Already at the first step.")
                continue
            state.current_step -= 1
            if state.completed_steps and state.completed_steps[-1] == _STEPS[state.current_step].label:
                state.completed_steps.pop()
            _persist_state(state)
            continue
        except WizardReset:
            _print("  Resetting wizard state.")
            _clear_wizard_state()
            return _WizardState()
        _print_step_diff(prev_config, state.config, step.label)
        if step.label not in state.completed_steps:
            state.completed_steps.append(step.label)
        state.current_step += 1
        _persist_state(state)
    return state


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def run_wizard() -> Optional[str]:
    """Run the interactive configuration wizard.

    Returns the path to the generated config file when the user opts
    to start training immediately, or ``None`` when the user defers —
    callers must handle both cases.
    """
    quickstart_path = _maybe_run_quickstart_template()
    if quickstart_path is not None:
        return _finalize_quickstart_path(quickstart_path)
    _print("\n  Falling back to the full configuration wizard.")
    return _run_full_wizard()


def _run_full_wizard() -> Optional[str]:
    """9-step interactive flow producing a hand-rolled config.yaml."""
    state = _maybe_resume_state()
    try:
        state = _drive_wizard_steps(state)
    except (KeyboardInterrupt, EOFError):
        _persist_state(state)
        _print(f"\n  Interrupted.  State preserved at {_wizard_state_path()} — rerun `forgelm --wizard` to resume.")
        return None
    config = _strip_internal_meta(state.config)
    config_filename = _prompt("Save config as", "my_config.yaml")
    if not config_filename.endswith((".yaml", ".yml")):
        config_filename += ".yaml"
    config_filename = _save_config_to_file(config, config_filename)
    _print_wizard_summary(config)
    _clear_wizard_state()
    if _prompt_yes_no("Start training now?", default=False):
        _print(f"\n  Running: forgelm --config {config_filename}")
        _print()
        return config_filename
    _print("\n  To start training later, run:")
    _print(f"    forgelm --config {config_filename}")
    _print()
    return None
