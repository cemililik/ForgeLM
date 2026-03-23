"""Interactive configuration wizard for ForgeLM.

Generates a valid config.yaml through step-by-step prompts.
No external dependencies required — uses stdlib input().
"""
import logging
import os
import sys
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


def run_wizard() -> str:
    """Run the interactive configuration wizard. Returns the path to the generated config file."""
    print("\n" + "=" * 60)
    print("  ForgeLM Configuration Wizard")
    print("=" * 60)

    # Step 1: Hardware Detection
    print("\n[1/6] Hardware Detection")
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
    print("\n[2/6] Model Selection")
    print("  Popular models:")
    for i, m in enumerate(POPULAR_MODELS, 1):
        print(f"    {i}) {m}")
    print(f"    {len(POPULAR_MODELS) + 1}) Custom (enter your own)")

    model_choice = input(f"  Choice [1]: ").strip()
    try:
        idx = int(model_choice) if model_choice else 1
        if idx <= len(POPULAR_MODELS):
            model_name = POPULAR_MODELS[idx - 1]
        else:
            model_name = _prompt("Enter HuggingFace model name or local path")
    except (ValueError, IndexError):
        model_name = POPULAR_MODELS[0]

    print(f"  Selected: {model_name}")

    # Step 3: Strategy Selection
    print("\n[3/6] Fine-Tuning Strategy")
    strategies = [
        "QLoRA (4-bit quantization — recommended, lowest memory)",
        "LoRA (full precision — more memory, slightly better quality)",
        "QLoRA + DoRA (4-bit + weight decomposition — best quality, more compute)",
    ]
    strategy = _prompt_choice("Choose your fine-tuning strategy:", strategies, default=1)

    load_in_4bit = "QLoRA" in strategy
    use_dora = "DoRA" in strategy

    # LoRA parameters
    target_preset = _prompt_choice(
        "Target modules:",
        ["standard (q_proj, v_proj)", "extended (q, k, v, o)", "full (all linear layers)"],
        default=1,
    )
    preset_key = target_preset.split(" ")[0]
    target_modules = TARGET_MODULE_PRESETS.get(preset_key, TARGET_MODULE_PRESETS["standard"])

    lora_r = int(_prompt("LoRA rank (r)", str(DEFAULT_LORA_R)))
    lora_alpha = int(_prompt("LoRA alpha", str(lora_r * 2)))

    # Step 4: Training Objective
    print("\n[4/7] Training Objective")
    objectives = [
        "SFT — Supervised Fine-Tuning (standard instruction tuning)",
        "DPO — Direct Preference Optimization (chosen/rejected pairs)",
        "SimPO — Simple Preference Optimization (no reference model, lower memory)",
        "KTO — Binary feedback alignment (thumbs up/down, practical for production)",
        "ORPO — Odds Ratio Preference Optimization (SFT + alignment in one stage)",
        "GRPO — Group Relative Policy Optimization (reasoning RL, like DeepSeek-R1)",
    ]
    objective = _prompt_choice("Choose your training objective:", objectives, default=1)
    trainer_type = objective.split(" — ")[0].strip().lower()

    # Dataset format guidance
    dataset_format_hint = {
        "sft": "Columns: System (opt), User/instruction, Assistant/output — or 'messages' list",
        "dpo": "Columns: prompt, chosen, rejected",
        "simpo": "Columns: prompt, chosen, rejected",
        "orpo": "Columns: prompt, chosen, rejected",
        "kto": "Columns: prompt, completion, label (boolean: true=good, false=bad)",
        "grpo": "Columns: prompt (model generates responses during training)",
    }
    print(f"  Dataset format: {dataset_format_hint.get(trainer_type, 'Standard format')}")

    # Step 5: Dataset
    print("\n[5/7] Dataset")
    dataset_path = _prompt("HuggingFace dataset name or local file path")

    # Step 6: Training Parameters
    print("\n[6/7] Training Parameters")
    epochs = int(_prompt("Number of epochs", str(DEFAULT_EPOCHS)))
    batch_size = int(_prompt("Batch size per device", str(DEFAULT_BATCH_SIZE)))
    max_length = int(_prompt("Max sequence length", str(DEFAULT_MAX_LENGTH)))
    output_dir = _prompt("Output directory", "./checkpoints")

    # Step 7: Build config
    print("\n[7/7] Output")

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
        },
        "data": {
            "dataset_name_or_path": dataset_path,
            "shuffle": True,
            "clean_text": True,
            "add_eos": True,
        },
    }

    # Optional: Webhook
    if _prompt_yes_no("Configure webhook notifications?", default=False):
        webhook_url = _prompt("Webhook URL (or leave empty for env var)")
        if webhook_url:
            config["webhook"] = {"url": webhook_url}
        else:
            env_var = _prompt("Environment variable name for webhook URL", "FORGELM_WEBHOOK_URL")
            config["webhook"] = {"url_env": env_var}

    # Optional: Evaluation
    if _prompt_yes_no("Enable auto-revert (discard model if quality drops)?", default=False):
        max_loss = _prompt("Max acceptable loss (leave empty for baseline-only)", "")
        config["evaluation"] = {
            "auto_revert": True,
            "max_acceptable_loss": float(max_loss) if max_loss else None,
        }

    # Save
    config_filename = _prompt("Save config as", "my_config.yaml")
    if not config_filename.endswith((".yaml", ".yml")):
        config_filename += ".yaml"

    try:
        with open(config_filename, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        print(f"\n  Config saved to: {config_filename}")
    except OSError as e:
        print(f"\n  Error: Could not save config to {config_filename}: {e}")
        config_filename = "my_config.yaml"
        with open(config_filename, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
        print(f"  Saved to fallback location: {config_filename}")

    # Summary
    print("\n" + "=" * 60)
    print("  Configuration Summary")
    print("=" * 60)
    print(f"  Model:    {model_name}")
    print(f"  Backend:  {suggested_backend}")
    print(f"  Strategy: {'QLoRA' if load_in_4bit else 'LoRA'}{' + DoRA' if use_dora else ''}")
    print(f"  Trainer:  {trainer_type.upper()}")
    print(f"  LoRA:     r={lora_r}, alpha={lora_alpha}")
    print(f"  Dataset:  {dataset_path}")
    print(f"  Epochs:   {epochs}, Batch: {batch_size}")
    print(f"  Output:   {output_dir}/final_model")
    print()

    # Quick run
    if _prompt_yes_no("Start training now?", default=False):
        print(f"\n  Running: forgelm --config {config_filename}")
        print()
        return config_filename
    else:
        print(f"\n  To start training later, run:")
        print(f"    forgelm --config {config_filename}")
        print()
        return None
