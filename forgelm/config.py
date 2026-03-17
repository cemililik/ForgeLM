import yaml
import os
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class ModelConfig(BaseModel):
    name_or_path: str
    max_length: int = 2048
    load_in_4bit: bool = True
    backend: str = "transformers"  # Can also be "unsloth"

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
    num_train_epochs: int = 3
    per_device_train_batch_size: int = 4
    gradient_accumulation_steps: int = 2
    learning_rate: float = 2e-5
    warmup_ratio: float = 0.1
    weight_decay: float = 0.01
    eval_steps: int = 200
    save_steps: int = 200
    save_total_limit: int = 3

class DataConfig(BaseModel):
    dataset_name_or_path: str
    shuffle: bool = True
    clean_text: bool = True
    add_eos: bool = True

class AuthConfig(BaseModel):
    hf_token: Optional[str] = None

class ForgeConfig(BaseModel):
    model: ModelConfig
    lora: LoraConfigModel
    training: TrainingConfig
    data: DataConfig
    auth: Optional[AuthConfig] = None

def load_config(config_path: str) -> ForgeConfig:
    """Loads and validates a YAML configuration file."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found at {config_path}")
        
    with open(config_path, 'r') as f:
        yaml_data = yaml.safe_load(f)
        
    # Pydantic handles validation and defaults automatically
    config = ForgeConfig(**yaml_data)
    return config
