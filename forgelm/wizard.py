"""Interactive configuration wizard for ForgeLM.

Generates a valid config.yaml through step-by-step prompts.
No external dependencies required — uses stdlib input().
"""

import logging
import os
import sys
from typing import Optional

import yaml

logger = logging.getLogger("forgelm.wizard")

# Defaults
DEFAULT_MAX_LENGTH = 2048
DEFAULT_LORA_R = 16
DEFAULT_LORA_ALPHA = 32
DEFAULT_DROPOUT = 0.1
DEFAULT_EPOCHS = 3
DEFAULT_BATCH_SIZE = 4
DEFAULT_LR = 2e-5

POPULAR_MODELS = [
    "meta-llama/Llama-3.1-8B-Instruct",
    "mistralai/Mistral-7B-Instruct-v0.3",
    "google/gemma-2-9b-it",
    "Qwen/Qwen2.5-7B-Instruct",
    "HuggingFaceTB/SmolLM2-1.7B-Instruct",
]

TARGET_MODULE_PRESETS = {
    "standard": ["q_proj", "v_proj"],
    "extended": ["q_proj", "k_proj", "v_proj", "o_proj"],
    "full": ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
}

# Common dataset-format hints for preference-based trainers (DPO/SimPO/ORPO)
_PREFERENCE_COLUMNS_HINT = "Columns: prompt, chosen, rejected"


def _prompt(question: str, default: str = "") -> str:
    """Prompt user with a default value."""
    suffix = f" [{default}]" if default else ""
    answer = input(f"  {question}{suffix}: ").strip()
    return answer if answer else default


def _prompt_choice(question: str, options: list, default: int = 1) -> str:
    """Prompt user to pick from numbered options."""
    print(f"\n  {question}")
    for i, opt in enumerate(options, 1):
        marker = " *" if i == default else ""
        print(f"    {i}) {opt}{marker}")
    choice = input(f"  Choice [{default}]: ").strip()
    try:
        idx = int(choice) if choice else default
        return options[idx - 1]
    except (ValueError, IndexError):
        return options[default - 1]


def _prompt_yes_no(question: str, default: bool = True) -> bool:
    """Prompt user for yes/no."""
    hint = "Y/n" if default else "y/N"
    answer = input(f"  {question} [{hint}]: ").strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes")


def _prompt_int(question: str, default: int, min_val: int = 1, max_val: int = 65536) -> int:
    """Prompt for an integer, re-asking until valid."""
    while True:
        raw = _prompt(question, str(default))
        try:
            val = int(raw)
            if min_val <= val <= max_val:
                return val
            print(f"    Value must be between {min_val} and {max_val}.")
        except ValueError:
            print("    Please enter a valid integer.")


def _detect_hardware() -> dict:
    """Detect GPU hardware if available."""
    info = {"gpu_available": False, "gpu_name": None, "vram_gb": None, "cuda_version": None}
    try:
        import torch

        if torch.cuda.is_available():
            info["gpu_available"] = True
            info["gpu_name"] = torch.cuda.get_device_name(0)
            info["vram_gb"] = round(torch.cuda.get_device_properties(0).total_mem / (1024**3), 1)
            info["cuda_version"] = torch.version.cuda
    except ImportError:
        pass
    return info


def _collect_rope_scaling(max_length: int) -> Optional[dict]:
    """Prompt for RoPE scaling parameters when context is long; otherwise None."""
    if max_length <= 4096:
        return None
    print(f"\n  Long context detected ({max_length} tokens).")
    if not _prompt_yes_no("Enable RoPE scaling for extended context?", default=True):
        return None
    rope_type = _prompt_choice(
        "RoPE scaling type:",
        ["linear (simple, proven)", "dynamic (adaptive)", "yarn (best quality, newer)"],
        default=1,
    )
    base_context = 4096
    rope_factor = max_length / base_context
    print(
        f"  Note: RoPE factor {rope_factor:.1f}x computed assuming base context of "
        f"{base_context} tokens. Adjust manually if your model has a different "
        f"original context length (e.g., Llama 3.1 = 131072, Mistral v0.3 = 32768)."
    )
    return {"type": rope_type.split(" ")[0], "factor": rope_factor}


def _collect_neftune_alpha() -> Optional[float]:
    """Prompt for NEFTune noise injection; returns alpha or None."""
    if not _prompt_yes_no("Enable NEFTune noise injection (improves training quality)?", default=False):
        return None
    return float(_prompt("NEFTune noise alpha", "5.0"))


def _collect_webhook_config() -> Optional[dict]:
    """Prompt for webhook configuration; returns the webhook section or None."""
    if not _prompt_yes_no("Configure webhook notifications?", default=False):
        return None
    webhook_url = _prompt("Webhook URL (or leave empty for env var)")
    if webhook_url:
        return {"url": webhook_url}
    env_var = _prompt("Environment variable name for webhook URL", "FORGELM_WEBHOOK_URL")
    return {"url_env": env_var}


def _collect_safety_config() -> Optional[dict]:
    """Prompt for safety eval; returns the safety section or None."""
    if not _prompt_yes_no("Enable safety evaluation (Llama Guard)?", default=False):
        return None
    scoring = _prompt_choice(
        "Safety scoring mode:",
        ["binary (simple safe/unsafe ratio)", "confidence_weighted (uses classifier confidence)"],
        default=1,
    )
    scoring_mode = "confidence_weighted" if "confidence" in scoring else "binary"
    safety_config: dict = {
        "enabled": True,
        "test_prompts": "configs/safety_prompts/general_safety.jsonl",
        "scoring": scoring_mode,
    }
    if scoring_mode == "confidence_weighted":
        safety_config["min_safety_score"] = 0.85
    if _prompt_yes_no("Track harm categories (S1-S14)?", default=False):
        safety_config["track_categories"] = True
        safety_config["severity_thresholds"] = {"critical": 0, "high": 0.01, "medium": 0.05}
    return safety_config


def _collect_evaluation_config() -> Optional[dict]:
    """Prompt for auto-revert + safety; returns the evaluation section or None."""
    if not _prompt_yes_no("Enable auto-revert (discard model if quality drops)?", default=False):
        return None
    max_loss = _prompt("Max acceptable loss (leave empty for baseline-only)", "")
    eval_config: dict = {
        "auto_revert": True,
        "max_acceptable_loss": float(max_loss) if max_loss else None,
    }
    safety = _collect_safety_config()
    if safety:
        eval_config["safety"] = safety
    return eval_config


def _collect_compliance_config() -> Optional[dict]:
    """Prompt for EU AI Act metadata; returns the compliance section or None."""
    if not _prompt_yes_no("Configure EU AI Act compliance metadata?", default=False):
        return None
    return {
        "provider_name": _prompt("Organization name"),
        "intended_purpose": _prompt("Intended purpose of the model"),
        "risk_classification": _prompt_choice(
            "Risk classification:",
            ["minimal-risk", "limited-risk", "high-risk"],
            default=1,
        ),
    }


def _save_config_to_file(config: dict, requested_filename: str) -> str:
    """Write *config* as YAML; falls back to a unique filename on OSError."""
    try:
        with open(requested_filename, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        print(f"\n  Config saved to: {requested_filename}")
        return requested_filename
    except OSError as e:
        print(f"\n  Error: Could not save config to {requested_filename}: {e}")

    # Pick a fallback that's guaranteed different from the path that just failed
    # (a hardcoded "my_config.yaml" would just re-raise the same OSError when
    # the original request was already that filename).
    from datetime import datetime as _dt

    base = os.path.splitext(os.path.basename(requested_filename))[0] or "my_config"
    fallback = os.path.join(os.path.expanduser("~"), f"{base}_{_dt.now().strftime('%Y%m%d_%H%M%S')}.yaml")
    try:
        with open(fallback, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        print(f"  Saved to fallback location: {fallback}")
        return fallback
    except OSError as e:
        print(f"  Fallback save also failed ({fallback}): {e}")
        raise


def _print_wizard_summary(
    *,
    model_name: str,
    suggested_backend: str,
    use_galore: bool,
    load_in_4bit: bool,
    use_dora: bool,
    trainer_type: str,
    lora_r: int,
    lora_alpha: int,
    dataset_path: str,
    epochs: int,
    batch_size: int,
    output_dir: str,
) -> None:
    """Pretty-print the chosen configuration before the start-now prompt."""
    print("\n" + "=" * 60)
    print("  Configuration Summary")
    print("=" * 60)
    print(f"  Model:    {model_name}")
    print(f"  Backend:  {suggested_backend}")
    if use_galore:
        strategy_str = "GaLore"
    elif load_in_4bit:
        strategy_str = "QLoRA"
    else:
        strategy_str = "LoRA"
    if use_dora:
        strategy_str += " + DoRA"
    print(f"  Strategy: {strategy_str}")
    print(f"  Trainer:  {trainer_type.upper()}")
    print(f"  LoRA:     r={lora_r}, alpha={lora_alpha}")
    print(f"  Dataset:  {dataset_path}")
    print(f"  Epochs:   {epochs}, Batch: {batch_size}")
    print(f"  Output:   {output_dir}/final_model")
    print()


def _select_model() -> str:
    """Prompt for a model from POPULAR_MODELS or allow a custom entry."""
    print("\n[2/8] Model Selection")
    print("  Popular models:")
    for i, m in enumerate(POPULAR_MODELS, 1):
        print(f"    {i}) {m}")
    print(f"    {len(POPULAR_MODELS) + 1}) Custom (enter your own)")
    model_choice = input("  Choice [1]: ").strip()
    try:
        idx = int(model_choice) if model_choice else 1
        if idx <= len(POPULAR_MODELS):
            return POPULAR_MODELS[idx - 1]
        return _prompt("Enter HuggingFace model name or local path")
    except (ValueError, IndexError):
        return POPULAR_MODELS[0]


def _derive_strategy_flags(strategy: str) -> tuple:
    """Decode the strategy menu choice into (load_in_4bit, use_dora, use_galore)."""
    return ("QLoRA" in strategy, "DoRA" in strategy, "GaLore" in strategy)


def _parse_trainer_type(objective: str) -> tuple:
    """Return (trainer_type, dataset_format_hint) for the chosen objective."""
    trainer_type = objective.split(" — ")[0].strip().lower()
    dataset_format_hint = {
        "sft": "Columns: System (opt), User/instruction, Assistant/output — or 'messages' list",
        "dpo": _PREFERENCE_COLUMNS_HINT,
        "simpo": _PREFERENCE_COLUMNS_HINT,
        "orpo": _PREFERENCE_COLUMNS_HINT,
        "kto": "Columns: prompt, completion, label (boolean: true=good, false=bad)",
        "grpo": "Columns: prompt (model generates responses during training)",
    }
    hint = dataset_format_hint.get(trainer_type, "Standard format")
    return trainer_type, hint


def _collect_galore_config(use_galore: bool) -> dict:
    """Prompt for GaLore-specific knobs when GaLore was selected; otherwise empty."""
    if not use_galore:
        print("\n[7/8] Advanced Options")
        return {}
    print("\n[7/8] GaLore Configuration")
    galore_rank = _prompt_int("GaLore rank (lower = less memory)", 128, min_val=1, max_val=4096)
    galore_optim = _prompt_choice(
        "GaLore optimizer:",
        ["galore_adamw (standard)", "galore_adamw_8bit (less memory)", "galore_adafactor (experimental)"],
        default=1,
    )
    return {
        "galore_enabled": True,
        "galore_optim": galore_optim.split(" ")[0],
        "galore_rank": galore_rank,
        "galore_update_proj_gap": 200,
        "galore_scale": 0.25,
    }


def run_wizard() -> Optional[str]:
    """Run the interactive configuration wizard.

    Returns the path to the generated config file when the user opts to start
    training immediately, or ``None`` when the user defers — callers must
    handle both cases.
    """
    print("\n" + "=" * 60)
    print("  ForgeLM Configuration Wizard")
    print("=" * 60)

    # Step 1: Hardware Detection
    print("\n[1/8] Hardware Detection")
    hw = _detect_hardware()
    if hw["gpu_available"]:
        print(f"  GPU detected: {hw['gpu_name']} ({hw['vram_gb']} GB VRAM, CUDA {hw['cuda_version']})")
    else:
        print("  No GPU detected. Training will use CPU (very slow for real workloads).")

    # Suggest backend
    suggested_backend = "transformers"
    if hw["gpu_available"]:
        if sys.platform == "linux":
            suggested_backend = "unsloth"
            print("  Recommended backend: unsloth (Linux + GPU detected)")
        else:
            print("  Recommended backend: transformers (Unsloth requires Linux)")

    # Step 2: Model Selection
    model_name = _select_model()
    print(f"  Selected: {model_name}")

    # Step 3: Strategy Selection
    print("\n[3/8] Fine-Tuning Strategy")
    strategies = [
        "QLoRA (4-bit quantization — recommended, lowest memory)",
        "LoRA (full precision — more memory, slightly better quality)",
        "QLoRA + DoRA (4-bit + weight decomposition — best quality, more compute)",
        "GaLore (full-parameter training via gradient projection — no adapters, lowest peak VRAM)",
    ]
    strategy = _prompt_choice("Choose your fine-tuning strategy:", strategies, default=1)
    load_in_4bit, use_dora, use_galore = _derive_strategy_flags(strategy)

    # LoRA parameters
    target_preset = _prompt_choice(
        "Target modules:",
        ["standard (q_proj, v_proj)", "extended (q, k, v, o)", "full (all linear layers)"],
        default=1,
    )
    preset_key = target_preset.split(" ")[0]
    target_modules = TARGET_MODULE_PRESETS.get(preset_key, TARGET_MODULE_PRESETS["standard"])

    lora_r = _prompt_int("LoRA rank (r)", DEFAULT_LORA_R, min_val=1, max_val=512)
    lora_alpha = _prompt_int("LoRA alpha", lora_r * 2, min_val=1, max_val=1024)

    # Step 4: Training Objective
    print("\n[4/8] Training Objective")
    objectives = [
        "SFT — Supervised Fine-Tuning (standard instruction tuning)",
        "DPO — Direct Preference Optimization (chosen/rejected pairs)",
        "SimPO — Simple Preference Optimization (no reference model, lower memory)",
        "KTO — Binary feedback alignment (thumbs up/down, practical for production)",
        "ORPO — Odds Ratio Preference Optimization (SFT + alignment in one stage)",
        "GRPO — Group Relative Policy Optimization (reasoning RL, like DeepSeek-R1)",
    ]
    objective = _prompt_choice("Choose your training objective:", objectives, default=1)
    trainer_type, dataset_format_hint = _parse_trainer_type(objective)
    print(f"  Dataset format: {dataset_format_hint}")

    # Step 5: Dataset
    print("\n[5/8] Dataset")
    dataset_path = _prompt("HuggingFace dataset name or local file path")

    # Step 6: Training Parameters
    print("\n[6/8] Training Parameters")
    epochs = _prompt_int("Number of epochs", DEFAULT_EPOCHS, min_val=1, max_val=1000)
    batch_size = _prompt_int("Batch size per device", DEFAULT_BATCH_SIZE, min_val=1, max_val=512)
    max_length = _prompt_int("Max sequence length", DEFAULT_MAX_LENGTH, min_val=64, max_val=131072)
    output_dir = _prompt("Output directory", "./checkpoints")

    rope_scaling = _collect_rope_scaling(max_length)
    neftune_alpha = _collect_neftune_alpha()
    use_neftune = neftune_alpha is not None

    use_oom_recovery = _prompt_yes_no(
        "Enable OOM recovery? (auto-halves batch size on CUDA out-of-memory, then retries)",
        default=False,
    )

    # Step 7: GaLore parameters (if selected)
    galore_config = _collect_galore_config(use_galore)

    # Step 8: Build config
    print("\n[8/8] Output")

    config = {
        "model": {
            "name_or_path": model_name,
            "max_length": max_length,
            "load_in_4bit": load_in_4bit,
            "backend": suggested_backend,
            "trust_remote_code": False,
        },
        "lora": {
            "r": lora_r,
            "alpha": lora_alpha,
            "dropout": DEFAULT_DROPOUT,
            "bias": "none",
            "use_dora": use_dora,
            "target_modules": target_modules,
            "task_type": "CAUSAL_LM",
        },
        "training": {
            "output_dir": output_dir,
            "final_model_dir": "final_model",
            "merge_adapters": False,
            "trainer_type": trainer_type,
            "num_train_epochs": epochs,
            "per_device_train_batch_size": batch_size,
            "gradient_accumulation_steps": 2,
            "learning_rate": DEFAULT_LR,
            "warmup_ratio": 0.1,
            "weight_decay": 0.01,
            "eval_steps": 200,
            "save_steps": 200,
            "save_total_limit": 3,
            "packing": False,
            **galore_config,
            **({"neftune_noise_alpha": neftune_alpha} if use_neftune else {}),
            **({"rope_scaling": rope_scaling} if rope_scaling else {}),
            **({"oom_recovery": True, "oom_recovery_min_batch_size": 1} if use_oom_recovery else {}),
        },
        "data": {
            "dataset_name_or_path": dataset_path,
            "shuffle": True,
            "clean_text": True,
            "add_eos": True,
        },
    }

    webhook_section = _collect_webhook_config()
    if webhook_section:
        config["webhook"] = webhook_section

    evaluation_section = _collect_evaluation_config()
    if evaluation_section:
        config["evaluation"] = evaluation_section

    compliance_section = _collect_compliance_config()
    if compliance_section:
        config["compliance"] = compliance_section

    # Save
    config_filename = _prompt("Save config as", "my_config.yaml")
    if not config_filename.endswith((".yaml", ".yml")):
        config_filename += ".yaml"
    config_filename = _save_config_to_file(config, config_filename)

    _print_wizard_summary(
        model_name=model_name,
        suggested_backend=suggested_backend,
        use_galore=use_galore,
        load_in_4bit=load_in_4bit,
        use_dora=use_dora,
        trainer_type=trainer_type,
        lora_r=lora_r,
        lora_alpha=lora_alpha,
        dataset_path=dataset_path,
        epochs=epochs,
        batch_size=batch_size,
        output_dir=output_dir,
    )

    # Quick run
    if _prompt_yes_no("Start training now?", default=False):
        print(f"\n  Running: forgelm --config {config_filename}")
        print()
        return config_filename
    else:
        print("\n  To start training later, run:")
        print(f"    forgelm --config {config_filename}")
        print()
        return None
