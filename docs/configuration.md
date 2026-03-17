# Configuration Guide

ForgeLM uses YAML files for all configuration, allowing for deterministic, repeatable training runs without requiring interactive shell prompts.

## Example Base Configuration (`config_template.yaml`)

```yaml
model:
  name_or_path: "meta-llama/Llama-2-7b-hf"
  max_length: 2048

lora:
  r: 8
  alpha: 16
  dropout: 0.1
  bias: "none"
  target_modules: 
    - "q_proj"
    - "v_proj"
  task_type: "CAUSAL_LM"

training:
  output_dir: "./checkpoints"
  num_train_epochs: 3
  per_device_train_batch_size: 4
  gradient_accumulation_steps: 2
  learning_rate: 2.0e-5
  warmup_ratio: 0.1
  weight_decay: 0.01
  eval_steps: 200
  save_steps: 200
  save_total_limit: 3

data:
  dataset_name_or_path: "your_huggingface_dataset_org/dataset_name"
  shuffle: true
  clean_text: true
  add_eos: true

auth:
  hf_token: "hf_YOUR_SECRET_TOKEN"
```

## Schema Details

### `model`
- **`name_or_path`**: (Required) The Hugging Face repo ID (e.g., `mistralai/Mistral-7B-v0.1`) or a local directory path to the base model.
- **`max_length`**: (Integer) Maximum context length for the tokenizer.

### `lora`
Defines Parameter-Efficient Fine-Tuning strategies.
- **`r`**: LoRA attention dimension (rank). Higher = more parameters.
- **`alpha`**: The alpha parameter for LoRA scaling.
- **`dropout`**: Dropout probability for LoRA layers.
- **`bias`**: Bias type for LoRA. Can be `'none'`, `'all'`, or `'lora_only'`.
- **`target_modules`**: List of model modules to apply LoRA. Often `["q_proj", "k_proj", "v_proj", "o_proj"]`.

### `training`
Defines Hyperparameters.
- **`output_dir`**: Directory where checkpoints are saved during training.
- **`learning_rate`**: The initial learning rate for AdamW optimizer.
- **`per_device_train_batch_size`**: Batch size per GPU core/device.
- **`gradient_accumulation_steps`**: Number of updates steps to accumulate before a backward/update pass.

### `data`
- **`dataset_name_or_path`**: Hugging face repository ID (e.g. `timdettmers/openassistant-guanaco`) or a local path to a JSON/CSV file.
- **`clean_text`**: Strips duplicate blank spaces.
- **`add_eos`**: Injects an End-Of-Sequence token to the dataset labels.

### `auth` (Optional)
- **`hf_token`**: Your Hugging Face access token for accessing private or gated models (like Llama-2/3). It's generally safer to omit this and use the `HUGGINGFACE_TOKEN` environment variable in production.
