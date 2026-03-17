import yaml
import os
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class ModelConfig(BaseModel):
    name_or_path: str
    max_length: int = 2048
    load_in_4bit: bool = True
    backend: str = "transformers"  # Can also be "unsloth"
    # Optional advanced bitsandbytes knobs (Transformers backend)
    bnb_4bit_use_double_quant: bool = True
    bnb_4bit_quant_type: str = "nf4"  # typically "nf4"
    bnb_4bit_compute_dtype: str = "auto"  # "auto" | "bfloat16" | "float16" | "float32"

class LoraConfigModel(BaseModel):
    r: int = 8
    alpha: int = 16
    dropout: float = 0.1
    bias: str = "none"
    use_dora: bool = False
    target_modules: List[str] = ["q_proj", "v_proj"]
    task_type: str = "CAUSAL_LM"

class TrainingConfig(BaseModel):
    output_dir: str = "./checkpoints"
    final_model_dir: str = "final_model"
    num_train_epochs: int = 3
    per_device_train_batch_size: int = 4
    gradient_accumulation_steps: int = 2
    learning_rate: float = 2e-5
    warmup_ratio: float = 0.1
    weight_decay: float = 0.01
    eval_steps: int = 200
    save_steps: int = 200
    save_total_limit: int = 3
    packing: bool = False

class DataConfig(BaseModel):
    dataset_name_or_path: str
    shuffle: bool = True
    clean_text: bool = True
    add_eos: bool = True

class EvaluationConfig(BaseModel):
    auto_revert: bool = False
    max_acceptable_loss: Optional[float] = None
    baseline_loss: Optional[float] = None  # if not provided, computed automatically (when validation exists)

class WebhookConfig(BaseModel):
    url: Optional[str] = None
    url_env: Optional[str] = None
    notify_on_start: bool = True
    notify_on_success: bool = True
    notify_on_failure: bool = True

class AuthConfig(BaseModel):
    hf_token: Optional[str] = None

class ForgeConfig(BaseModel):
    model: ModelConfig
    lora: LoraConfigModel
    training: TrainingConfig
    data: DataConfig
    auth: Optional[AuthConfig] = None
    evaluation: Optional[EvaluationConfig] = None
    webhook: Optional[WebhookConfig] = None

def load_config(config_path: str) -> ForgeConfig:
    """Loads and validates a YAML configuration file."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found at {config_path}")
        
    with open(config_path, 'r') as f:
        yaml_data = yaml.safe_load(f)
        
    # Pydantic handles validation and defaults automatically
    config = ForgeConfig(**yaml_data)
    return config
