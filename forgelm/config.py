import yaml
import logging
import os
from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Dict, Any

logger = logging.getLogger("forgelm.config")

class ModelConfig(BaseModel):
    name_or_path: str
    max_length: int = 2048
    load_in_4bit: bool = True
    backend: str = "transformers"  # Can also be "unsloth"
    trust_remote_code: bool = False  # Security: disabled by default for enterprise safety
    offline: bool = False  # Air-gapped mode: no HF Hub calls, local models/datasets only
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
    merge_adapters: bool = False
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

class BenchmarkConfig(BaseModel):
    """Configuration for post-training benchmark evaluation via lm-evaluation-harness."""
    enabled: bool = False
    tasks: List[str] = []  # e.g. ["arc_easy", "hellaswag", "mmlu"]
    num_fewshot: Optional[int] = None  # task default if None
    batch_size: str = "auto"  # "auto" or integer string
    limit: Optional[int] = None  # limit samples per task (useful for quick checks)
    output_dir: Optional[str] = None  # save benchmark results JSON; defaults to training output_dir
    min_score: Optional[float] = None  # minimum average accuracy; triggers revert if below

class EvaluationConfig(BaseModel):
    auto_revert: bool = False
    max_acceptable_loss: Optional[float] = None
    baseline_loss: Optional[float] = None  # if not provided, computed automatically (when validation exists)
    benchmark: Optional[BenchmarkConfig] = None  # post-training benchmark via lm-eval-harness

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

    @model_validator(mode="after")
    def _validate_consistency(self):
        # Warn about potential config issues
        if self.evaluation and self.evaluation.auto_revert and self.training.merge_adapters:
            logger.warning(
                "auto_revert=True with merge_adapters=True: if evaluation fails, "
                "the merged full model will be deleted. Consider using adapter-only saves."
            )
        if self.model.backend == "unsloth" and self.model.trust_remote_code:
            logger.warning(
                "trust_remote_code is ignored when using the Unsloth backend."
            )
        return self


class ConfigError(Exception):
    """Raised when configuration validation fails."""
    pass


def load_config(config_path: str) -> ForgeConfig:
    """Loads and validates a YAML configuration file."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path, 'r') as f:
        try:
            yaml_data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML syntax in {config_path}: {e}") from e

    if not isinstance(yaml_data, dict):
        raise ConfigError(f"Configuration file must contain a YAML mapping, got {type(yaml_data).__name__}")

    try:
        config = ForgeConfig(**yaml_data)
    except Exception as e:
        raise ConfigError(f"Configuration validation failed: {e}") from e

    return config
