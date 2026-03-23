# Configuration Guide

ForgeLM uses YAML files for all configuration, allowing for deterministic, repeatable training runs without requiring interactive shell prompts.

## Example Base Configuration (`config_template.yaml`)

```yaml
model:
  name_or_path: "meta-llama/Llama-2-7b-hf"
  max_length: 2048
  load_in_4bit: true
  backend: "transformers" # Can be "unsloth" for 2x faster training
  # Optional advanced bitsandbytes knobs (Transformers backend + 4bit):
  # bnb_4bit_use_double_quant: true
  # bnb_4bit_quant_type: "nf4"
  # bnb_4bit_compute_dtype: "auto"   # auto|bfloat16|float16|float32

lora:
  r: 8
  alpha: 16
  dropout: 0.1
  bias: "none"
  use_dora: false
  target_modules: 
    - "q_proj"
    - "v_proj"
  task_type: "CAUSAL_LM"

training:
  output_dir: "./checkpoints"
  final_model_dir: "final_model"
  merge_adapters: false
  num_train_epochs: 3
  per_device_train_batch_size: 4
  gradient_accumulation_steps: 2
  learning_rate: 2.0e-5
  warmup_ratio: 0.1
  weight_decay: 0.01
  eval_steps: 200
  save_steps: 200
  save_total_limit: 3
  packing: false

data:
  dataset_name_or_path: "your_huggingface_dataset_org/dataset_name"
  shuffle: true
  clean_text: true
  add_eos: true

auth:
  hf_token: "hf_YOUR_SECRET_TOKEN"

evaluation:
  auto_revert: false
  max_acceptable_loss: 2.5
  baseline_loss: null # Computed automatically if null

webhook:
  url: "https://your-webhook-endpoint.com/api/notify"
  notify_on_start: true
  notify_on_success: true
  notify_on_failure: true
```

## Schema Details

### `model`
- **`name_or_path`**: (Required) The Hugging Face repo ID (e.g., `mistralai/Mistral-7B-v0.1`) or a local directory path to the base model.
- **`max_length`**: (Integer) Maximum context length for the tokenizer.
- **`load_in_4bit`**: (Boolean) Enables QLoRA 4-bit (NF4) quantization to drastically reduce memory usage. Default is `true`.
- **`backend`**: (String) Engine used for training. `'transformers'` is standard. Change to `'unsloth'` for 2x-5x faster training speeds (requires the unsloth library).
- **`trust_remote_code`**: (Boolean) Allows execution of custom code from model repositories. Default is `false` for security. Only enable for models that explicitly require it (e.g., some custom architectures). **Warning:** Enabling this in production or air-gapped environments is a security risk.

### `lora`
Defines Parameter-Efficient Fine-Tuning strategies.
- **`r`**: LoRA attention dimension (rank). Higher = more parameters.
- **`alpha`**: The alpha parameter for LoRA scaling.
- **`dropout`**: Dropout probability for LoRA layers.
- **`bias`**: Bias type for LoRA. Can be `'none'`, `'all'`, or `'lora_only'`.
- **`use_dora`**: (Boolean) Enables Weight-Decomposed Low-Rank Adaptation (DoRA), dynamically separating parameter magnitude and direction for better performance at the same rank. Default is `false`.
- **`target_modules`**: List of model modules to apply LoRA. Often `["q_proj", "k_proj", "v_proj", "o_proj"]`.

### `training`
Defines Hyperparameters.
- **`output_dir`**: Directory where checkpoints are saved during training.
- **`final_model_dir`**: Subdirectory under `output_dir` for final artifacts (defaults to `final_model`).
- **`merge_adapters`**: If `false` (default), saves adapter-only artifacts. If `true`, attempts to merge adapters and save a full model.
- **`learning_rate`**: The initial learning rate for AdamW optimizer.
- **`per_device_train_batch_size`**: Batch size per GPU core/device.
- **`gradient_accumulation_steps`**: Number of updates steps to accumulate before a backward/update pass.
- **`packing`**: Enables sequence packing in TRL `SFTTrainer` (advanced; keep `false` unless you know your data supports it).

### `data`
- **`dataset_name_or_path`**: Hugging face repository ID (e.g. `timdettmers/openassistant-guanaco`) or a local path to a JSON/CSV file.
- **`clean_text`**: Strips duplicate blank spaces.
- **`add_eos`**: Injects an End-Of-Sequence token to the dataset labels.

### `auth` (Optional)
- **`hf_token`**: Your Hugging Face access token for accessing private or gated models (like Llama-2/3). It's generally safer to omit this and use the `HUGGINGFACE_TOKEN` environment variable in production.

### `evaluation` (Optional)
Configuration for automated quality checks after training.
- **`auto_revert`**: (Boolean) If `true`, deletes the checkpoints if the final loss exceeds `max_acceptable_loss`. Default is `false`.
- **`max_acceptable_loss`**: (Float) The threshold for failing the training run Based on evaluation loss. 
- **`baseline_loss`**: (Float) Optional baseline. If not set, ForgeLM computes it from the validation set before training starts.

### `webhook` (Optional)
ForgeLM can send JSON payloads to an external service to track training progress.
- **`url`**: The destination URL (POST request).
- **`url_env`**: Alternatively, specify the name of an environment variable containing the URL.
- **`notify_on_start`**: (Boolean) Send notification when training begins.
- **`notify_on_success`**: (Boolean) Send notification on successful completion.
- **`notify_on_failure`**: (Boolean) Send notification if the pipeline crashes or evaluation fails.

#### Webhook Payload Format
ForgeLM sends a JSON body with the following structure:
```json
{
  "status": "started | success | failure",
  "run_name": "model-name_finetune",
  "message": "Step description...",
  "metrics": {
    "loss": 1.25,
    "epoch": 3.0
  }
}
```
