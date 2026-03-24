import logging
from typing import Any, Tuple

import torch
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

logger = logging.getLogger("forgelm.model")


def _resolve_bnb_compute_dtype(dtype_str: str):
    if not dtype_str or dtype_str == "auto":
        return torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    normalized = str(dtype_str).lower()
    if normalized in ("bf16", "bfloat16"):
        return torch.bfloat16
    if normalized in ("fp16", "float16"):
        return torch.float16
    if normalized in ("fp32", "float32"):
        return torch.float32
    raise ValueError(f"Unsupported bnb_4bit_compute_dtype: {dtype_str!r}")


def get_model_and_tokenizer(config: Any) -> Tuple[Any, Any]:
    """Loads the base model, tokenizer, and configures LoRA."""
    logger.info("Loading Base Model: %s with backend: %s", config.model.name_or_path, config.model.backend)

    trust_remote_code = getattr(config.model, "trust_remote_code", False)
    if trust_remote_code:
        logger.warning(
            "trust_remote_code is ENABLED. This allows execution of arbitrary code "
            "from the model repository. Only use this with models you trust."
        )

    # --- UNSLOTH BACKEND ---
    if config.model.backend.lower() == "unsloth":
        try:
            from unsloth import FastLanguageModel
        except ImportError as e:
            raise ImportError("Unsloth backend selected but 'unsloth' is not installed. Please install it.") from e

        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=config.model.name_or_path,
            max_seq_length=config.model.max_length,
            dtype=None,  # Auto detection
            load_in_4bit=config.model.load_in_4bit,
        )

        logger.info("Setting up Unsloth LoRA configuration (DoRA=%s)...", config.lora.use_dora)
        model = FastLanguageModel.get_peft_model(
            model,
            r=config.lora.r,
            target_modules=config.lora.target_modules,
            lora_alpha=config.lora.alpha,
            lora_dropout=config.lora.dropout,
            bias=config.lora.bias,
            use_gradient_checkpointing="unsloth",
            use_rslora=getattr(config.lora, "use_rslora", False),
            use_dora=config.lora.use_dora,
        )

        return model, tokenizer

    # --- MULTIMODAL VLM CHECK ---
    mm_cfg = getattr(config.model, "multimodal", None)
    is_multimodal = mm_cfg and mm_cfg.enabled
    if is_multimodal:
        logger.info("Multimodal VLM mode enabled — loading with AutoProcessor.")

    # --- TRANSFORMERS BACKEND ---
    if is_multimodal:
        from transformers import AutoProcessor

        tokenizer = AutoProcessor.from_pretrained(config.model.name_or_path, trust_remote_code=trust_remote_code)
    else:
        tokenizer = AutoTokenizer.from_pretrained(config.model.name_or_path, trust_remote_code=trust_remote_code)
    if hasattr(tokenizer, "pad_token") and tokenizer.pad_token is None:
        logger.info("Tokenizer has no pad_token, using eos_token as pad_token.")
        tokenizer.pad_token = tokenizer.eos_token

    # Distributed training (DeepSpeed/FSDP) manages device placement itself.
    # device_map="auto" conflicts with multi-GPU distributed strategies.
    dist_cfg = getattr(config, "distributed", None)
    is_distributed = dist_cfg and dist_cfg.strategy

    model_kwargs = {
        "trust_remote_code": trust_remote_code,
    }
    if not is_distributed:
        model_kwargs["device_map"] = "auto"
    else:
        logger.info("Distributed training detected — skipping device_map='auto'.")

    if torch.cuda.is_available() and config.model.load_in_4bit:
        logger.info("Using 4-bit QLoRA quantization...")
        compute_dtype = _resolve_bnb_compute_dtype(getattr(config.model, "bnb_4bit_compute_dtype", "auto"))
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=bool(getattr(config.model, "bnb_4bit_use_double_quant", True)),
            bnb_4bit_quant_type=str(getattr(config.model, "bnb_4bit_quant_type", "nf4")),
            bnb_4bit_compute_dtype=compute_dtype,
        )
        model_kwargs["quantization_config"] = bnb_config

    model = AutoModelForCausalLM.from_pretrained(config.model.name_or_path, **model_kwargs)

    # enable_input_require_grads is needed for gradient checkpointing with LoRA
    if hasattr(model, "enable_input_require_grads"):
        model.enable_input_require_grads()

    if torch.cuda.is_available() and config.model.load_in_4bit:
        model = prepare_model_for_kbit_training(model)

    # Resolve PEFT method
    peft_method = getattr(config.lora, "method", "lora")
    use_dora = config.lora.use_dora or peft_method == "dora"
    use_rslora = getattr(config.lora, "use_rslora", False) or peft_method == "rslora"

    # Detect and configure MoE architecture
    moe_cfg = getattr(config.model, "moe", None)
    if moe_cfg and hasattr(model.config, "num_local_experts"):
        num_experts = model.config.num_local_experts
        logger.info("MoE model detected: %d experts", num_experts)

        if moe_cfg.quantize_experts:
            _apply_moe_expert_quantization(model, num_experts)

        if moe_cfg.experts_to_train != "all":
            _freeze_unselected_experts(model, moe_cfg.experts_to_train, num_experts)

    logger.info(
        "Setting up PEFT configuration (method=%s, DoRA=%s, rsLoRA=%s)...",
        peft_method,
        use_dora,
        use_rslora,
    )

    lora_kwargs = dict(
        r=config.lora.r,
        lora_alpha=config.lora.alpha,
        lora_dropout=config.lora.dropout,
        bias=config.lora.bias,
        task_type=config.lora.task_type,
        target_modules=config.lora.target_modules,
        use_dora=use_dora,
        use_rslora=use_rslora,
    )

    # PiSSA initialization
    if peft_method == "pissa":
        lora_kwargs["init_lora_weights"] = "pissa"
        logger.info("Using PiSSA initialization (principal component adapter init).")

    lora_config = LoraConfig(**lora_kwargs)
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()

    return model, tokenizer


def _apply_moe_expert_quantization(model, num_experts: int) -> None:
    """Reduce MoE expert memory by freezing and converting to half precision.

    Converts frozen expert weights to float16/bfloat16 for VRAM savings.
    Note: True int8 quantization requires bitsandbytes Linear8bitLt —
    raw dtype casting to int8 destroys weight values and is NOT used here.
    """
    optimized_count = 0
    target_dtype = torch.float16
    if torch.cuda.is_available() and torch.cuda.is_bf16_supported():
        target_dtype = torch.bfloat16

    for name, module in model.named_modules():
        if "expert" in name.lower() and hasattr(module, "weight"):
            if not module.weight.requires_grad:
                try:
                    if module.weight.dtype != target_dtype:
                        module.weight.data = module.weight.data.to(target_dtype)
                        optimized_count += 1
                except Exception as e:
                    logger.debug("Could not optimize %s: %s", name, e)

    if optimized_count > 0:
        logger.info(
            "MoE expert optimization: %d expert weight tensors converted to %s for VRAM savings.",
            optimized_count,
            target_dtype,
        )
    else:
        logger.info(
            "MoE expert optimization: no frozen expert weights found. "
            "Optimization applies after LoRA freezes non-target parameters."
        )


def _freeze_unselected_experts(model, experts_to_train: str, num_experts: int) -> None:
    """Freeze all expert parameters except the selected ones.

    Args:
        model: The model with MoE architecture.
        experts_to_train: Comma-separated expert indices (e.g., "0,1,2").
        num_experts: Total number of experts in the model.
    """
    try:
        selected = {int(idx.strip()) for idx in experts_to_train.split(",")}
    except ValueError:
        logger.warning(
            "Invalid experts_to_train value: '%s'. Expected comma-separated integers. Training all experts.",
            experts_to_train,
        )
        return

    invalid = selected - set(range(num_experts))
    if invalid:
        logger.warning("Expert indices %s exceed num_experts=%d. Ignoring invalid indices.", invalid, num_experts)
        selected -= invalid

    frozen_count = 0
    for name, param in model.named_parameters():
        # Match expert module patterns: experts.0, experts.1, etc.
        if "expert" in name.lower():
            # Extract expert index from parameter name
            for i in range(num_experts):
                if f"experts.{i}." in name or f"expert_{i}." in name:
                    if i not in selected:
                        param.requires_grad = False
                        frozen_count += 1
                    break

    logger.info(
        "MoE expert selection: training experts %s, froze %d parameters from unselected experts.",
        sorted(selected),
        frozen_count,
    )
