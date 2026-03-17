import torch
from typing import Tuple, Any
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

try:
    from peft import prepare_model_for_int8_training
except ImportError:
    prepare_model_for_int8_training = None

def get_model_and_tokenizer(config: Any) -> Tuple[AutoModelForCausalLM, AutoTokenizer]:
    """Loads the base model, tokenizer, and configures LoRA."""
    print(f"Loading Base Model: {config.model.name_or_path}")

    tokenizer = AutoTokenizer.from_pretrained(config.model.name_or_path, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # Setup bitsandbytes configs or 8bit training parameters depending on PyTorch capabilities
    model_kwargs = {
        "device_map": "auto",
        "trust_remote_code": True,
    }
    
    if torch.cuda.is_available():
        model_kwargs["load_in_8bit"] = True
    
    model = AutoModelForCausalLM.from_pretrained(
        config.model.name_or_path,
        **model_kwargs
    )
    
    if torch.cuda.is_available():
        if hasattr(model, "enable_input_require_grads"):
            model.enable_input_require_grads()
        model = prepare_model_for_kbit_training(model)
        
    print("Setting up LoRA configuration...")
    lora_config = LoraConfig(
        r=config.lora.r,
        lora_alpha=config.lora.alpha,
        lora_dropout=config.lora.dropout,
        bias=config.lora.bias,
        task_type=config.lora.task_type,
        target_modules=config.lora.target_modules
    )
    
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()
    
    return model, tokenizer
