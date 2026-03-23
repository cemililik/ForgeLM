import logging
import torch
from typing import Tuple, Any
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

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
        except ImportError:
            raise ImportError("Unsloth backend selected but 'unsloth' is not installed. Please install it.")

        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=config.model.name_or_path,
            max_seq_length=config.model.max_length,
            dtype=None, # Auto detection
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
            use_rslora=False,
            use_dora=config.lora.use_dora,
        )

        return model, tokenizer

    # --- TRANSFORMERS BACKEND ---
    tokenizer = AutoTokenizer.from_pretrained(config.model.name_or_path, trust_remote_code=trust_remote_code)
    if tokenizer.pad_token is None:
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

    model = AutoModelForCausalLM.from_pretrained(
        config.model.name_or_path,
        **model_kwargs
    )

    if torch.cuda.is_available() and config.model.load_in_4bit:
        if hasattr(model, "enable_input_require_grads"):
            model.enable_input_require_grads()
        model = prepare_model_for_kbit_training(model)

    # Resolve PEFT method
    peft_method = getattr(config.lora, "method", "lora")
    use_dora = config.lora.use_dora or peft_method == "dora"
    use_rslora = getattr(config.lora, "use_rslora", False) or peft_method == "rslora"

    # Detect MoE architecture
    moe_cfg = getattr(config.model, "moe", None)
    if moe_cfg and hasattr(model.config, "num_local_experts"):
        num_experts = model.config.num_local_experts
        logger.info("MoE model detected: %d experts", num_experts)
        if moe_cfg.quantize_experts:
            logger.info("Expert quantization enabled for VRAM savings.")

    logger.info("Setting up PEFT configuration (method=%s, DoRA=%s, rsLoRA=%s)...",
                peft_method, use_dora, use_rslora)

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
