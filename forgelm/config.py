import logging
import os
from typing import Any, Dict, List, Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

logger = logging.getLogger("forgelm.config")


class MoeConfig(BaseModel):
    """MoE-specific fine-tuning configuration."""

    model_config = ConfigDict(extra="forbid")

    quantize_experts: bool = False  # quantize inactive experts for VRAM savings
    experts_to_train: str = "all"  # "all" or comma-separated expert indices


class MultimodalConfig(BaseModel):
    """VLM multimodal fine-tuning configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    image_column: str = "image"  # column name for image paths/URLs
    text_column: str = "text"  # column name for text/captions


class MergeConfig(BaseModel):
    """Post-training model merging configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    method: str = "ties"  # "ties", "dare", "slerp", "linear"
    models: List[Dict[str, Any]] = []  # list of {path, weight} dicts
    output_dir: str = "./merged_model"


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    bnb_4bit_quant_type: Literal["nf4", "fp4"] = "nf4"
    bnb_4bit_compute_dtype: str = "auto"  # "auto" | "bfloat16" | "float16" | "float32"

    @model_validator(mode="after")
    def _warn_float32_qlora(self):
        if (
            self.load_in_4bit
            and isinstance(self.bnb_4bit_compute_dtype, str)
            and self.bnb_4bit_compute_dtype.lower() in ("fp32", "float32")
        ):
            logger.warning(
                "bnb_4bit_compute_dtype='float32' with load_in_4bit=True negates most VRAM savings. "
                "Consider 'bfloat16' or 'auto'."
            )
        return self


class LoraConfigModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    r: int = 8
    alpha: int = 16
    dropout: float = 0.1
    bias: str = "none"
    method: Literal["lora", "dora", "pissa", "rslora"] = "lora"
    use_dora: bool = False  # kept for backward compat; method="dora" also works
    use_rslora: bool = False  # rank-stabilized LoRA for high ranks (r>64)
    target_modules: List[str] = ["q_proj", "v_proj"]
    task_type: str = "CAUSAL_LM"

    @model_validator(mode="after")
    def _normalize_peft_method(self):
        if self.use_dora and self.method == "lora":
            logger.warning(
                "lora.use_dora=True is deprecated. Use method='dora' instead. Automatically setting method='dora'."
            )
            object.__setattr__(self, "method", "dora")
        if self.use_rslora and self.method == "lora":
            logger.warning(
                "lora.use_rslora=True is deprecated. Use method='rslora' instead. "
                "Automatically setting method='rslora'."
            )
            object.__setattr__(self, "method", "rslora")
        return self


class TrainingConfig(BaseModel):
    # populate_by_name lets users keep the legacy `grpo_max_new_tokens` field
    # name in their YAML even though the canonical attribute is now
    # `grpo_max_completion_length` (matches TRL's GRPOConfig field). Without
    # this flag, Pydantic would only accept the alias on input, never the
    # canonical name.
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    output_dir: str = "./checkpoints"
    final_model_dir: str = "final_model"
    merge_adapters: bool = False
    trainer_type: str = "sft"  # "sft", "orpo", "dpo", "simpo", "kto", "grpo"
    max_steps: int = -1  # -1 = use num_train_epochs; positive value overrides epochs
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
    early_stopping_patience: int = 3
    # --- Alignment trainer parameters ---
    orpo_beta: float = 0.1  # ORPO odds ratio weight
    dpo_beta: float = 0.1  # DPO temperature parameter
    simpo_gamma: float = 0.5  # SimPO margin term
    simpo_beta: float = 2.0  # SimPO scaling parameter
    kto_beta: float = 0.1  # KTO loss parameter
    grpo_num_generations: int = 4  # GRPO: number of responses to generate per prompt
    # TRL >=0.12 renamed `max_new_tokens` to `max_completion_length` on GRPOConfig.
    # We mirror the TRL spelling, but accept the legacy name via Pydantic alias
    # so existing YAML configs and templates keep working without edits.
    grpo_max_completion_length: int = Field(
        default=512,
        alias="grpo_max_new_tokens",
        description="GRPO: max tokens per generated completion (TRL field name).",
    )
    grpo_reward_model: Optional[str] = (
        # GRPO: HF model path for reward scoring. When None, the trainer wires
        # `combined_format_length_reward` as a baseline (always-on, gradient-rich
        # format + length shaping signal). If the dataset additionally carries a
        # `gold_answer` field (see the grpo-math template), a regex correctness
        # reward is appended for additive scoring — TRL sums multiple reward funcs.
        None
    )
    # --- GaLore (optimizer-level memory optimization, alternative to LoRA) ---
    galore_enabled: bool = False
    galore_optim: str = "galore_adamw"  # galore_adamw, galore_adamw_8bit, galore_adafactor, + _layerwise variants
    galore_rank: int = 128  # Low-rank subspace dimension for gradient projection
    galore_update_proj_gap: int = 200  # Steps between SVD re-computations
    galore_scale: float = 0.25  # Gradient scaling factor (analogous to LoRA alpha)
    galore_proj_type: str = "std"  # "std", "reverse_std", "right", "left", "full"
    galore_target_modules: Optional[List[str]] = None  # Regex list; None = auto [r".*.attn.*", r".*.mlp.*"]
    # --- Long-context optimizations ---
    rope_scaling: Optional[Dict[str, Any]] = (
        None  # RoPE scaling config: {"type": "linear"|"dynamic"|"yarn"|"longrope", "factor": 4.0}
    )
    neftune_noise_alpha: Optional[float] = (
        None  # NEFTune: add noise to embeddings (5.0 is a common value, improves quality)
    )
    sliding_window_attention: Optional[int] = None  # Override model's sliding window size (e.g. 4096 for Mistral)
    sample_packing: bool = False  # Pack multiple short sequences into one (saves compute, requires packing=true)
    # --- OOM recovery ---
    oom_recovery: bool = False  # Auto-halve batch size on CUDA OOM and retry
    oom_recovery_min_batch_size: int = 1  # Stop retrying when batch size reaches this value
    # --- Tracking ---
    report_to: Literal["tensorboard", "wandb", "mlflow", "none"] = "tensorboard"
    run_name: Optional[str] = None  # W&B/MLflow run name; auto-generated if None
    # --- Cost estimation ---
    gpu_cost_per_hour: Optional[float] = None  # $/hour for GPU; None = auto-detect from known GPUs


class DistributedConfig(BaseModel):
    """Configuration for multi-GPU distributed training via DeepSpeed or FSDP."""

    model_config = ConfigDict(extra="forbid")

    strategy: Optional[str] = None  # values: deepspeed, fsdp, or None for single-GPU
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

    model_config = ConfigDict(extra="forbid")

    collection_method: str = ""
    annotation_process: str = ""
    known_biases: str = ""
    personal_data_included: bool = False
    dpia_completed: bool = False  # Data Protection Impact Assessment


class DataConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_name_or_path: str
    extra_datasets: Optional[List[str]] = None  # additional datasets to mix in
    mix_ratio: Optional[List[float]] = None  # weight per dataset (primary + extras); uniform if None
    shuffle: bool = True
    clean_text: bool = True
    add_eos: bool = True
    governance: Optional[DataGovernanceConfig] = None  # Art. 10: data governance metadata

    @field_validator("mix_ratio")
    @classmethod
    def _validate_mix_ratio(cls, v):
        if v is not None:
            if any(r < 0 for r in v):
                raise ValueError("mix_ratio values must be non-negative.")
            if all(r == 0 for r in v):
                raise ValueError("mix_ratio values cannot all be zero.")
        return v


class BenchmarkConfig(BaseModel):
    """Configuration for post-training benchmark evaluation via lm-evaluation-harness."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    tasks: List[str] = []  # e.g. ["arc_easy", "hellaswag", "mmlu"]
    num_fewshot: Optional[int] = None  # task default if None
    batch_size: str = "auto"  # "auto" or integer string
    limit: Optional[int] = None  # limit samples per task (useful for quick checks)
    output_dir: Optional[str] = None  # save benchmark results JSON; defaults to training output_dir
    min_score: Optional[float] = None  # minimum average accuracy; triggers revert if below


class SafetyConfig(BaseModel):
    """Post-training safety evaluation configuration."""

    model_config = ConfigDict(extra="forbid")

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

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    judge_model: str = "gpt-4o"  # API model name or local model path
    judge_api_key_env: Optional[str] = None  # env var name for API key; None = local judge
    judge_api_base: Optional[str] = None
    eval_dataset: str = "eval_prompts.jsonl"  # evaluation prompts file
    min_score: float = 5.0  # minimum average score (1-10 scale)


class EvaluationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auto_revert: bool = False
    max_acceptable_loss: Optional[float] = None
    baseline_loss: Optional[float] = None  # if not provided, computed automatically (when validation exists)
    benchmark: Optional[BenchmarkConfig] = None  # post-training benchmark via lm-eval-harness
    safety: Optional[SafetyConfig] = None  # post-training safety evaluation
    llm_judge: Optional[JudgeConfig] = None  # LLM-as-Judge scoring
    require_human_approval: bool = False  # Art. 14: pause pipeline for human review before final save


class RiskAssessmentConfig(BaseModel):
    """Art. 9: Risk management — declare risks before training."""

    model_config = ConfigDict(extra="forbid")

    intended_use: str = ""
    foreseeable_misuse: List[str] = []
    risk_category: str = "minimal-risk"  # "high-risk", "limited-risk", "minimal-risk"
    mitigation_measures: List[str] = []
    vulnerable_groups_considered: bool = False


class MonitoringConfig(BaseModel):
    """Art. 12+17: Post-market monitoring hooks."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    endpoint: str = ""  # monitoring system webhook URL
    endpoint_env: Optional[str] = None  # env var name for endpoint URL
    metrics_export: str = "none"  # "none", "prometheus", "datadog", "custom_webhook"
    alert_on_drift: bool = True
    check_interval_hours: int = 24


class ComplianceMetadataConfig(BaseModel):
    """Art. 11 + Annex IV: Provider and system metadata for technical documentation."""

    model_config = ConfigDict(extra="forbid")

    provider_name: str = ""
    provider_contact: str = ""
    system_name: str = ""
    intended_purpose: str = ""
    known_limitations: str = ""
    system_version: str = ""
    risk_classification: str = "minimal-risk"  # "high-risk", "limited-risk", "minimal-risk"


class SyntheticConfig(BaseModel):
    """Synthetic data generation via teacher→student distillation."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    teacher_model: str = ""  # HF model path or API model name (e.g., "gpt-4", "meta-llama/Llama-3-70B")
    teacher_backend: Literal["api", "local", "file"] = "api"
    api_base: str = ""  # API endpoint (e.g., "https://api.openai.com/v1")
    api_key: Optional[str] = None  # API key (prefer api_key_env for security)
    api_key_env: Optional[str] = None  # Env var name for API key (e.g., "OPENAI_API_KEY")
    api_delay: float = 0.5  # Seconds between API calls (rate limiting)
    api_timeout: int = 60  # API call timeout in seconds
    seed_file: str = ""  # Path to seed prompts file (JSONL or plain text, one per line)
    seed_prompts: List[str] = []  # Inline seed prompts (alternative to seed_file)
    system_prompt: str = ""  # System prompt for teacher model
    max_new_tokens: int = 1024  # Max tokens per teacher response
    temperature: float = 0.7  # Generation temperature
    output_file: str = "synthetic_data.jsonl"  # Output JSONL file path
    output_format: Literal["messages", "instruction", "chatml", "prompt_response"] = "messages"

    @model_validator(mode="after")
    def _warn_direct_api_key(self):
        if self.api_key and not self.api_key_env:
            logger.warning(
                "synthetic.api_key is set directly in config. "
                "Prefer api_key_env to avoid accidentally committing secrets to version control."
            )
        return self

    def model_dump(self, **kwargs):
        """Redact api_key from serialized output."""
        d = super().model_dump(**kwargs)
        if d.get("api_key"):
            d["api_key"] = "***REDACTED***"
        return d


class WebhookConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: Optional[str] = None
    url_env: Optional[str] = None
    notify_on_start: bool = True
    notify_on_success: bool = True
    notify_on_failure: bool = True
    timeout: int = 5  # HTTP request timeout in seconds


class AuthConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    model_config = ConfigDict(extra="forbid")

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
    synthetic: Optional[SyntheticConfig] = None

    def _warn_general_consistency(self) -> None:
        """Emit warnings for the broad cross-field config inconsistencies."""
        if self.evaluation and self.evaluation.auto_revert and self.training.merge_adapters:
            logger.warning(
                "auto_revert=True with merge_adapters=True: if evaluation fails, "
                "the merged full model will be deleted. Consider using adapter-only saves."
            )
        if self.model.backend == "unsloth" and self.model.trust_remote_code:
            logger.warning(
                "trust_remote_code=True with Unsloth backend: Unsloth internally calls "
                "HuggingFace Transformers which MAY still execute remote code. "
                "Verify the Unsloth version's behavior before production use."
            )
        if self.training.merge_adapters and self.training.trainer_type != "sft":
            logger.warning(
                "merge_adapters=True with trainer_type='%s' may produce unexpected results. "
                "Adapter merging is designed for SFT workflows.",
                self.training.trainer_type,
            )
        if self.lora.r > 64 and not getattr(self.lora, "use_rslora", False) and self.lora.method not in ("rslora",):
            logger.warning(
                "LoRA rank r=%d is high. Consider method='rslora' for training stability.",
                self.lora.r,
            )
        if (
            self.training.eval_steps
            and self.training.save_steps
            and self.training.eval_steps > self.training.save_steps
            and self.evaluation
            and getattr(self.evaluation, "auto_revert", False)
        ):
            logger.warning(
                "eval_steps (%d) > save_steps (%d): load_best_model_at_end may not work correctly. "
                "Set eval_steps <= save_steps.",
                self.training.eval_steps,
                self.training.save_steps,
            )

    def _warn_high_risk_compliance(self) -> None:
        """EU AI Act high-risk compliance recommendations."""
        is_high_risk = (self.risk_assessment and self.risk_assessment.risk_category == "high-risk") or (
            self.compliance and self.compliance.risk_classification == "high-risk"
        )
        if not is_high_risk:
            return
        if not self.evaluation or not self.evaluation.auto_revert:
            logger.warning(
                "High-risk AI classification requires evaluation.auto_revert: true "
                "for EU AI Act compliance. Safety gates should be enabled."
            )
        safety = self.evaluation.safety if self.evaluation else None
        if not safety or not safety.enabled:
            logger.warning(
                "High-risk AI classification: safety evaluation is strongly recommended. "
                "Set evaluation.safety.enabled: true."
            )
        elif not safety.track_categories:
            logger.warning(
                "High-risk AI: harm category tracking (track_categories: true) is recommended "
                "for detailed EU AI Act compliance documentation."
            )

    def _validate_trainer_type(self) -> None:
        valid_trainers = {"sft", "orpo", "dpo", "simpo", "kto", "grpo"}
        if self.training.trainer_type not in valid_trainers:
            raise ValueError(
                f"Invalid trainer_type: '{self.training.trainer_type}'. "
                f"Must be one of: {', '.join(sorted(valid_trainers))}"
            )

    def _validate_galore(self) -> None:
        if not self.training.galore_enabled:
            return
        valid_galore_optims = {
            "galore_adamw",
            "galore_adamw_8bit",
            "galore_adafactor",
            "galore_adamw_layerwise",
            "galore_adamw_8bit_layerwise",
            "galore_adafactor_layerwise",
        }
        if self.training.galore_optim not in valid_galore_optims:
            raise ValueError(
                f"Invalid galore_optim: '{self.training.galore_optim}'. "
                f"Must be one of: {', '.join(sorted(valid_galore_optims))}"
            )
        if self.lora.r > 0:
            logger.info(
                "GaLore (gradient rank=%d) enabled alongside LoRA (adapter rank=%d). "
                "GaLore reduces gradient memory via low-rank projection; "
                "LoRA constrains trainable parameters. Both are active simultaneously.",
                self.training.galore_rank,
                self.lora.r,
            )
        if "layerwise" in self.training.galore_optim and self.distributed and self.distributed.strategy:
            raise ValueError(
                "GaLore layerwise optimizers do not support multi-GPU (DDP). "
                "Use a non-layerwise variant (e.g., galore_adamw) or disable distributed training."
            )

    def _validate_distributed(self) -> None:
        if not (self.distributed and self.distributed.strategy):
            return
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

    @model_validator(mode="after")
    def _validate_consistency(self):
        self._warn_general_consistency()
        self._warn_high_risk_compliance()
        self._validate_trainer_type()
        self._validate_galore()
        self._validate_distributed()
        return self


class ConfigError(Exception):
    """Raised when configuration validation fails."""

    pass


def load_config(config_path: str) -> ForgeConfig:
    """Loads and validates a YAML configuration file."""
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
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
