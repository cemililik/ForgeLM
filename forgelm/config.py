import logging
import os
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, model_validator

logger = logging.getLogger("forgelm.config")


class MoeConfig(BaseModel):
    """MoE-specific fine-tuning configuration."""

    quantize_experts: bool = False  # quantize inactive experts for VRAM savings
    experts_to_train: str = "all"  # "all" or comma-separated expert indices


class MultimodalConfig(BaseModel):
    """VLM multimodal fine-tuning configuration."""

    enabled: bool = False
    image_column: str = "image"  # column name for image paths/URLs
    text_column: str = "text"  # column name for text/captions


class MergeConfig(BaseModel):
    """Post-training model merging configuration."""

    enabled: bool = False
    method: str = "ties"  # "ties", "dare", "slerp", "linear"
    models: List[Dict[str, Any]] = []  # list of {path, weight} dicts
    output_dir: str = "./merged_model"


class ModelConfig(BaseModel):
    name_or_path: str
    max_length: int = 2048
    load_in_4bit: bool = True
    backend: str = "transformers"  # Can also be "unsloth"
    trust_remote_code: bool = False  # Security: disabled by default for enterprise safety
    offline: bool = False  # Air-gapped mode: no HF Hub calls, local models/datasets only
    moe: Optional[MoeConfig] = None  # MoE-specific settings
    multimodal: Optional[MultimodalConfig] = None  # VLM fine-tuning settings
    # Optional advanced bitsandbytes knobs (Transformers backend)
    bnb_4bit_use_double_quant: bool = True
    bnb_4bit_quant_type: str = "nf4"  # typically "nf4"
    bnb_4bit_compute_dtype: str = "auto"  # "auto" | "bfloat16" | "float16" | "float32"


class LoraConfigModel(BaseModel):
    r: int = 8
    alpha: int = 16
    dropout: float = 0.1
    bias: str = "none"
    method: str = "lora"  # "lora", "dora", "pissa", "rslora"
    use_dora: bool = False  # kept for backward compat; method="dora" also works
    use_rslora: bool = False  # rank-stabilized LoRA for high ranks (r>64)
    target_modules: List[str] = ["q_proj", "v_proj"]
    task_type: str = "CAUSAL_LM"


class TrainingConfig(BaseModel):
    output_dir: str = "./checkpoints"
    final_model_dir: str = "final_model"
    merge_adapters: bool = False
    trainer_type: str = "sft"  # "sft", "orpo", "dpo", "simpo", "kto", "grpo"
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
    # --- Alignment trainer parameters ---
    orpo_beta: float = 0.1  # ORPO odds ratio weight
    dpo_beta: float = 0.1  # DPO temperature parameter
    simpo_gamma: float = 0.5  # SimPO margin term
    simpo_beta: float = 2.0  # SimPO scaling parameter
    kto_beta: float = 0.1  # KTO loss parameter
    grpo_num_generations: int = 4  # GRPO: number of responses to generate per prompt
    grpo_max_new_tokens: int = 512  # GRPO: max tokens per generated response
    grpo_reward_model: Optional[str] = (
        None  # GRPO: HF model path for reward scoring (None = use default verifiable rewards)
    )
    # --- Tracking ---
    report_to: str = "tensorboard"  # "tensorboard", "wandb", "mlflow", or "none"
    run_name: Optional[str] = None  # W&B/MLflow run name; auto-generated if None


class DistributedConfig(BaseModel):
    """Configuration for multi-GPU distributed training via DeepSpeed or FSDP."""

    strategy: Optional[str] = None  # "deepspeed" or "fsdp"; None = single-GPU
    # --- DeepSpeed ---
    deepspeed_config: Optional[str] = None  # path to DS JSON or preset name: "zero2", "zero3", "zero3_offload"
    # --- FSDP ---
    fsdp_strategy: str = "full_shard"  # "full_shard", "shard_grad_op", "no_shard", "hybrid_shard"
    fsdp_auto_wrap: bool = True  # auto wrap transformer layers
    fsdp_offload: bool = False  # offload parameters to CPU
    fsdp_backward_prefetch: str = "backward_pre"  # "backward_pre" or "backward_post"
    fsdp_state_dict_type: str = "FULL_STATE_DICT"  # "FULL_STATE_DICT" or "SHARDED_STATE_DICT"


class DataGovernanceConfig(BaseModel):
    """Art. 10: Data governance metadata."""

    collection_method: str = ""
    annotation_process: str = ""
    known_biases: str = ""
    personal_data_included: bool = False
    dpia_completed: bool = False  # Data Protection Impact Assessment


class DataConfig(BaseModel):
    dataset_name_or_path: str
    extra_datasets: Optional[List[str]] = None  # additional datasets to mix in
    mix_ratio: Optional[List[float]] = None  # weight per dataset (primary + extras); uniform if None
    shuffle: bool = True
    clean_text: bool = True
    add_eos: bool = True
    governance: Optional[DataGovernanceConfig] = None  # Art. 10: data governance metadata


class BenchmarkConfig(BaseModel):
    """Configuration for post-training benchmark evaluation via lm-evaluation-harness."""

    enabled: bool = False
    tasks: List[str] = []  # e.g. ["arc_easy", "hellaswag", "mmlu"]
    num_fewshot: Optional[int] = None  # task default if None
    batch_size: str = "auto"  # "auto" or integer string
    limit: Optional[int] = None  # limit samples per task (useful for quick checks)
    output_dir: Optional[str] = None  # save benchmark results JSON; defaults to training output_dir
    min_score: Optional[float] = None  # minimum average accuracy; triggers revert if below


class SafetyConfig(BaseModel):
    """Post-training safety evaluation configuration."""

    enabled: bool = False
    classifier: str = "meta-llama/Llama-Guard-3-8B"  # safety classifier model
    test_prompts: str = "safety_prompts.jsonl"  # adversarial test prompts file
    max_safety_regression: float = 0.05  # max allowed unsafe ratio (0.0–1.0)
    # Phase 9: Advanced scoring
    scoring: str = "binary"  # "binary" (default) or "confidence_weighted"
    min_safety_score: Optional[float] = (
        None  # weighted score threshold (0.0-1.0), used when scoring="confidence_weighted"
    )
    min_classifier_confidence: float = 0.7  # flag responses below this confidence
    track_categories: bool = False  # parse Llama Guard S1-S14 harm categories
    severity_thresholds: Optional[Dict[str, float]] = None  # per-severity limits: {"critical": 0, "high": 0.01}


class JudgeConfig(BaseModel):
    """LLM-as-Judge evaluation configuration."""

    enabled: bool = False
    judge_model: str = "gpt-4o"  # API model name or local model path
    judge_api_key_env: Optional[str] = None  # env var name for API key; None = local judge
    eval_dataset: str = "eval_prompts.jsonl"  # evaluation prompts file
    min_score: float = 5.0  # minimum average score (1-10 scale)


class EvaluationConfig(BaseModel):
    auto_revert: bool = False
    max_acceptable_loss: Optional[float] = None
    baseline_loss: Optional[float] = None  # if not provided, computed automatically (when validation exists)
    benchmark: Optional[BenchmarkConfig] = None  # post-training benchmark via lm-eval-harness
    safety: Optional[SafetyConfig] = None  # post-training safety evaluation
    llm_judge: Optional[JudgeConfig] = None  # LLM-as-Judge scoring
    require_human_approval: bool = False  # Art. 14: pause pipeline for human review before final save


class RiskAssessmentConfig(BaseModel):
    """Art. 9: Risk management — declare risks before training."""

    intended_use: str = ""
    foreseeable_misuse: List[str] = []
    risk_category: str = "minimal-risk"  # "high-risk", "limited-risk", "minimal-risk"
    mitigation_measures: List[str] = []
    vulnerable_groups_considered: bool = False


class MonitoringConfig(BaseModel):
    """Art. 12+17: Post-market monitoring hooks."""

    enabled: bool = False
    endpoint: str = ""  # monitoring system webhook URL
    endpoint_env: Optional[str] = None  # env var name for endpoint URL
    metrics_export: str = "none"  # "none", "prometheus", "datadog", "custom_webhook"
    alert_on_drift: bool = True
    check_interval_hours: int = 24


class ComplianceMetadataConfig(BaseModel):
    """Art. 11 + Annex IV: Provider and system metadata for technical documentation."""

    provider_name: str = ""
    provider_contact: str = ""
    system_name: str = ""
    intended_purpose: str = ""
    known_limitations: str = ""
    system_version: str = ""
    risk_classification: str = "minimal-risk"  # "high-risk", "limited-risk", "minimal-risk"


class WebhookConfig(BaseModel):
    url: Optional[str] = None
    url_env: Optional[str] = None
    notify_on_start: bool = True
    notify_on_success: bool = True
    notify_on_failure: bool = True
    timeout: int = 5  # HTTP request timeout in seconds


class AuthConfig(BaseModel):
    hf_token: Optional[str] = None

    def __repr__(self) -> str:
        return "AuthConfig(hf_token='***')" if self.hf_token else "AuthConfig(hf_token=None)"

    def model_dump(self, **kwargs):
        """Override to always exclude token from serialization."""
        data = super().model_dump(**kwargs)
        if "hf_token" in data and data["hf_token"]:
            data["hf_token"] = "***REDACTED***"
        return data


class ForgeConfig(BaseModel):
    model: ModelConfig
    lora: LoraConfigModel
    training: TrainingConfig
    data: DataConfig
    auth: Optional[AuthConfig] = None
    evaluation: Optional[EvaluationConfig] = None
    webhook: Optional[WebhookConfig] = None
    distributed: Optional[DistributedConfig] = None
    merge: Optional[MergeConfig] = None
    compliance: Optional[ComplianceMetadataConfig] = None
    risk_assessment: Optional[RiskAssessmentConfig] = None
    monitoring: Optional[MonitoringConfig] = None

    @model_validator(mode="after")
    def _validate_consistency(self):
        # Warn about potential config issues
        if self.evaluation and self.evaluation.auto_revert and self.training.merge_adapters:
            logger.warning(
                "auto_revert=True with merge_adapters=True: if evaluation fails, "
                "the merged full model will be deleted. Consider using adapter-only saves."
            )
        if self.model.backend == "unsloth" and self.model.trust_remote_code:
            logger.warning("trust_remote_code is ignored when using the Unsloth backend.")
        # High-risk compliance enforcement
        is_high_risk = (self.risk_assessment and self.risk_assessment.risk_category == "high-risk") or (
            self.compliance and self.compliance.risk_classification == "high-risk"
        )
        if is_high_risk:
            if not self.evaluation or not self.evaluation.auto_revert:
                logger.warning(
                    "High-risk AI classification requires evaluation.auto_revert: true "
                    "for EU AI Act compliance. Safety gates should be enabled."
                )
            if not self.evaluation or not self.evaluation.safety or not self.evaluation.safety.enabled:
                logger.warning(
                    "High-risk AI classification: safety evaluation is strongly recommended. "
                    "Set evaluation.safety.enabled: true."
                )
            if (
                self.evaluation
                and self.evaluation.safety
                and self.evaluation.safety.enabled
                and not self.evaluation.safety.track_categories
            ):
                logger.warning(
                    "High-risk AI: harm category tracking (track_categories: true) is recommended "
                    "for detailed EU AI Act compliance documentation."
                )
        # Trainer type validation
        valid_trainers = {"sft", "orpo", "dpo", "simpo", "kto", "grpo"}
        if self.training.trainer_type not in valid_trainers:
            raise ValueError(
                f"Invalid trainer_type: '{self.training.trainer_type}'. "
                f"Must be one of: {', '.join(sorted(valid_trainers))}"
            )
        # Distributed training validations
        if self.distributed and self.distributed.strategy:
            if self.model.backend == "unsloth":
                raise ValueError(
                    "Unsloth backend does not support multi-GPU distributed training. "
                    "Set backend: 'transformers' for DeepSpeed/FSDP."
                )
            if (
                self.distributed.strategy == "deepspeed"
                and self.distributed.deepspeed_config
                and "zero3" in str(self.distributed.deepspeed_config)
                and self.model.load_in_4bit
            ):
                logger.warning(
                    "QLoRA (4-bit) with DeepSpeed ZeRO-3 has known compatibility issues. "
                    "Consider using ZeRO-2 or disabling 4-bit quantization for stability."
                )
        return self


class ConfigError(Exception):
    """Raised when configuration validation fails."""

    pass


def load_config(config_path: str) -> ForgeConfig:
    """Loads and validates a YAML configuration file."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path, "r") as f:
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
