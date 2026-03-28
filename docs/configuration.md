# Configuration Guide

ForgeLM uses YAML files for all configuration — declarative, version-controllable, and CI/CD-ready.

See `config_template.yaml` for a complete annotated example.

---

## `model`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name_or_path` | string | *required* | HuggingFace model ID or local path |
| `max_length` | int | `2048` | Maximum context length |
| `load_in_4bit` | bool | `true` | Enable QLoRA 4-bit NF4 quantization |
| `backend` | string | `"transformers"` | `"transformers"` or `"unsloth"` (2-5x faster, Linux only) |
| `trust_remote_code` | bool | `false` | Allow custom code from model repos. **Security risk** — only enable for models that require it |
| `offline` | bool | `false` | Air-gapped mode: no HF Hub calls. Models/datasets must be local |
| `bnb_4bit_use_double_quant` | bool | `true` | Double quantization for extra VRAM savings |
| `bnb_4bit_quant_type` | string | `"nf4"` | Quantization type (`"nf4"` or `"fp4"`) |
| `bnb_4bit_compute_dtype` | string | `"auto"` | Compute dtype: `"auto"`, `"bfloat16"`, `"float16"`, `"float32"` |

#### `model.moe` (Optional — MoE models)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `quantize_experts` | bool | `false` | Quantize inactive expert weights to int8 for VRAM savings |
| `experts_to_train` | string | `"all"` | `"all"` or comma-separated expert indices (e.g., `"0,1,2"`) |

#### `model.multimodal` (Optional — VLM models)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | `false` | Enable vision-language model fine-tuning |
| `image_column` | string | `"image"` | Column name for image paths/URLs in dataset |
| `text_column` | string | `"text"` | Column name for text/captions |

---

## `lora`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `r` | int | `8` | LoRA rank. Higher = more parameters |
| `alpha` | int | `16` | LoRA scaling factor |
| `dropout` | float | `0.1` | Dropout probability |
| `bias` | string | `"none"` | `"none"`, `"all"`, or `"lora_only"` |
| `method` | string | `"lora"` | PEFT method: `"lora"`, `"dora"`, `"pissa"`, `"rslora"` |
| `use_dora` | bool | `false` | Enable DoRA (Weight-Decomposed LoRA) |
| `use_rslora` | bool | `false` | Rank-stabilized LoRA (recommended for r>64) |
| `target_modules` | list | `["q_proj", "v_proj"]` | Model modules to apply LoRA |
| `task_type` | string | `"CAUSAL_LM"` | Task type for PEFT |

---

## `training`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `output_dir` | string | `"./checkpoints"` | Checkpoint save directory |
| `final_model_dir` | string | `"final_model"` | Subdirectory for final artifacts |
| `merge_adapters` | bool | `false` | Merge adapters into base model before saving |
| `trainer_type` | string | `"sft"` | `"sft"`, `"dpo"`, `"simpo"`, `"kto"`, `"orpo"`, `"grpo"` |
| `num_train_epochs` | int | `3` | Number of training epochs |
| `per_device_train_batch_size` | int | `4` | Batch size per GPU |
| `gradient_accumulation_steps` | int | `2` | Steps to accumulate before backward pass |
| `learning_rate` | float | `2e-5` | Learning rate (lower for alignment: 5e-6) |
| `warmup_ratio` | float | `0.1` | Warmup proportion |
| `weight_decay` | float | `0.01` | AdamW weight decay |
| `eval_steps` | int | `200` | Evaluate every N steps |
| `save_steps` | int | `200` | Save checkpoint every N steps |
| `save_total_limit` | int | `3` | Max checkpoints to keep |
| `packing` | bool | `false` | Sequence packing (SFT only) |
| `report_to` | string | `"tensorboard"` | `"tensorboard"`, `"wandb"`, `"mlflow"`, `"none"` |
| `run_name` | string | `null` | W&B/MLflow run name (auto-generated if null) |

#### GaLore (Optimizer-Level Memory Optimization)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `galore_enabled` | bool | `false` | Enable GaLore gradient low-rank projection |
| `galore_optim` | string | `"galore_adamw_8bit"` | GaLore optimizer: `"galore_adamw"`, `"galore_adamw_8bit"`, `"galore_adafactor"` |
| `galore_rank` | int | `128` | Rank for gradient projection |
| `galore_update_proj_gap` | int | `200` | Steps between projection updates |
| `galore_scale` | float | `0.25` | GaLore scaling factor |
| `galore_proj_type` | string | `"std"` | Projection type: `"std"`, `"reverse_std"`, `"right"`, `"left"`, `"full"` |
| `galore_target_modules` | list | `["q_proj", "k_proj", "v_proj", "o_proj"]` | Modules to apply GaLore |

#### Long-Context Training

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `rope_scaling` | string | `null` | RoPE scaling method: `"linear"`, `"dynamic"` |
| `neftune_noise_alpha` | float | `null` | NEFTune noise injection alpha (e.g., `5.0`) |
| `sliding_window_attention` | int | `null` | Sliding window attention size in tokens |
| `sample_packing` | bool | `false` | Pack multiple short samples into full-length sequences |

#### GPU Cost Estimation

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `gpu_cost_per_hour` | float | `null` | Custom GPU cost rate (USD/hour). Auto-detected from GPU model if null |

#### Alignment Parameters

| Field | Type | Default | Used By |
|-------|------|---------|---------|
| `dpo_beta` | float | `0.1` | DPO temperature |
| `simpo_gamma` | float | `0.5` | SimPO margin term |
| `simpo_beta` | float | `2.0` | SimPO scaling |
| `kto_beta` | float | `0.1` | KTO loss parameter |
| `orpo_beta` | float | `0.1` | ORPO odds ratio weight |
| `grpo_num_generations` | int | `4` | GRPO: responses per prompt |
| `grpo_max_new_tokens` | int | `512` | GRPO: max response length |
| `grpo_reward_model` | string | `null` | GRPO: reward model path (HF or local) |

---

## `data`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `dataset_name_or_path` | string | *required* | HF dataset ID or local JSONL path |
| `extra_datasets` | list | `null` | Additional datasets to mix in |
| `mix_ratio` | list | `null` | Weight per dataset (e.g., `[0.7, 0.3]`) |
| `shuffle` | bool | `true` | Shuffle training data |
| `clean_text` | bool | `true` | Strip extra whitespace |
| `add_eos` | bool | `true` | Add EOS token to sequences |

#### `data.governance` (Optional — EU AI Act Art. 10)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `collection_method` | string | `""` | How data was collected |
| `annotation_process` | string | `""` | Annotation methodology |
| `known_biases` | string | `""` | Known dataset biases |
| `personal_data_included` | bool | `false` | Contains personal data |
| `dpia_completed` | bool | `false` | Data Protection Impact Assessment done |

---

## `evaluation` (Optional)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `auto_revert` | bool | `false` | Delete model if evaluation fails |
| `max_acceptable_loss` | float | `null` | Hard ceiling for eval_loss |
| `baseline_loss` | float | `null` | Computed automatically if null |
| `require_human_approval` | bool | `false` | Pause for human review (exit code 4) |

#### `evaluation.benchmark` (Optional)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | `false` | Enable lm-eval-harness benchmarks |
| `tasks` | list | `[]` | Task names (e.g., `["arc_easy", "hellaswag"]`) |
| `num_fewshot` | int | `null` | Few-shot examples (task default) |
| `batch_size` | string | `"auto"` | Evaluation batch size |
| `limit` | int | `null` | Samples per task (for quick checks) |
| `min_score` | float | `null` | Minimum average accuracy |

#### `evaluation.safety` (Optional)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | `false` | Enable safety classifier evaluation |
| `classifier` | string | `"meta-llama/Llama-Guard-3-8B"` | Safety classifier model |
| `test_prompts` | string | `"safety_prompts.jsonl"` | Adversarial test prompts file. Built-in sets in `configs/safety_prompts/` |
| `max_safety_regression` | float | `0.05` | Max allowed unsafe ratio (binary gate) |
| `scoring` | string | `"binary"` | Scoring mode: `"binary"` or `"confidence_weighted"` |
| `min_safety_score` | float | `null` | Weighted score threshold (0.0-1.0). Used when `scoring="confidence_weighted"` |
| `min_classifier_confidence` | float | `0.7` | Flag responses below this confidence for manual review |
| `track_categories` | bool | `false` | Parse Llama Guard S1-S14 harm categories |
| `severity_thresholds` | dict | `null` | Per-severity limits: `{"critical": 0, "high": 0.01, "medium": 0.05}` |

#### `evaluation.llm_judge` (Optional)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | `false` | Enable LLM-as-Judge scoring |
| `judge_model` | string | `"gpt-4o"` | Judge model (API or local path) |
| `judge_api_key_env` | string | `null` | Env var name for API key (null = local) |
| `eval_dataset` | string | `"eval_prompts.jsonl"` | Evaluation prompts file |
| `min_score` | float | `5.0` | Minimum average score (1-10) |

---

## `webhook` (Optional)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | string | `null` | Webhook destination URL |
| `url_env` | string | `null` | Env var name containing URL |
| `notify_on_start` | bool | `true` | Notify on training start |
| `notify_on_success` | bool | `true` | Notify on success |
| `notify_on_failure` | bool | `true` | Notify on failure |
| `timeout` | int | `5` | HTTP request timeout (seconds) |

---

## `distributed` (Optional)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `strategy` | string | `null` | `"deepspeed"` or `"fsdp"` (null = single GPU) |
| `deepspeed_config` | string | `null` | Preset (`"zero2"`, `"zero3"`, `"zero3_offload"`) or JSON path |
| `fsdp_strategy` | string | `"full_shard"` | `"full_shard"`, `"shard_grad_op"`, `"hybrid_shard"`, `"no_shard"` |
| `fsdp_auto_wrap` | bool | `true` | Auto-wrap transformer layers |
| `fsdp_offload` | bool | `false` | Offload parameters to CPU |

---

## `merge` (Optional)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | `false` | Enable model merging |
| `method` | string | `"ties"` | `"ties"`, `"dare"`, `"slerp"`, `"linear"` |
| `models` | list | `[]` | List of `{path, weight}` dicts |
| `output_dir` | string | `"./merged_model"` | Output directory |

---

## `compliance` (Optional — EU AI Act Art. 11 + Annex IV)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `provider_name` | string | `""` | Organization name |
| `provider_contact` | string | `""` | Contact email |
| `system_name` | string | `""` | AI system name |
| `intended_purpose` | string | `""` | What the model is for |
| `known_limitations` | string | `""` | What it should not be used for |
| `system_version` | string | `""` | Version identifier |
| `risk_classification` | string | `"minimal-risk"` | `"high-risk"`, `"limited-risk"`, `"minimal-risk"` |

---

## `risk_assessment` (Optional — EU AI Act Art. 9)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `intended_use` | string | `""` | Intended use description |
| `foreseeable_misuse` | list | `[]` | List of misuse scenarios |
| `risk_category` | string | `"minimal-risk"` | Risk classification |
| `mitigation_measures` | list | `[]` | Risk mitigation measures |
| `vulnerable_groups_considered` | bool | `false` | Impact on vulnerable groups assessed |

---

## `monitoring` (Optional — EU AI Act Art. 12+17)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | `false` | Enable monitoring hooks |
| `endpoint` | string | `""` | Monitoring webhook URL |
| `endpoint_env` | string | `null` | Env var name for endpoint |
| `metrics_export` | string | `"none"` | `"none"`, `"prometheus"`, `"datadog"`, `"custom_webhook"` |
| `alert_on_drift` | bool | `true` | Alert on model drift |
| `check_interval_hours` | int | `24` | Monitoring check interval |

---

## `synthetic` (Optional — Synthetic Data Generation)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | `false` | Enable synthetic data generation |
| `teacher_model` | string | `null` | Teacher model for distillation (HF ID or local path) |
| `teacher_backend` | string | `"api"` | Teacher backend: `"api"` (OpenAI-compatible) or `"local"` |
| `teacher_api_key_env` | string | `null` | Env var name for teacher API key |
| `teacher_api_base` | string | `null` | Custom API base URL for teacher |
| `seed_file` | string | `null` | Path to seed prompts file (JSONL) |
| `output_file` | string | `"synthetic_data.jsonl"` | Output file for generated data |
| `num_samples` | int | `100` | Number of samples to generate |
| `max_tokens` | int | `512` | Max tokens per generated response |
| `temperature` | float | `0.7` | Sampling temperature for generation |
| `top_p` | float | `0.9` | Top-p (nucleus) sampling |
| `system_prompt` | string | `null` | System prompt for the teacher model |
| `output_format` | string | `"sft"` | Output format: `"sft"`, `"dpo"`, `"conversation"` |
| `batch_size` | int | `10` | Batch size for API calls |
| `retry_attempts` | int | `3` | Number of retries on API failure |
| `timeout` | int | `60` | API request timeout (seconds) |

---

## `auth` (Optional)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `hf_token` | string | `null` | HuggingFace token (prefer `HUGGINGFACE_TOKEN` env var) |
