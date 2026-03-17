# Usage Guide

ForgeLM is designed to be executed via a command-line interface, making it perfect for both local experimentation and remote GPU execution (RunPod, Lambda Labs, AWS).

## Prerequisites

Ensure you have a machine with an NVIDIA GPU and CUDA installed. While ForgeLM will attempt to operate in CPU mode, training LLMs effectively requires a GPU.

```bash
git clone https://github.com/cemililik/ForgeLM.git
cd ForgeLM
python3 -m pip install -e .
```

### Optional installs

- Enable QLoRA dependencies (Linux):

```bash
python3 -m pip install -e ".[qlora]"
```

- Enable Unsloth backend (Linux):

```bash
python3 -m pip install -e ".[unsloth]"
```

- Enable Phase 2 evaluation/benchmark dependencies:

```bash
python3 -m pip install -e ".[eval]"
```

## Authentication

If you are using gated models (like Meta's Llama family) or private datasets, you must authenticate. ForgeLM checks for authentication in this order:

1. **Config File**: If `hf_token: "xxx"` is present in your yaml under the `auth:` block.
2. **Environment Variable**: `export HUGGINGFACE_TOKEN="hf_xxxxx"`
3. **Local Cache**: If you have run `huggingface-cli login` previously on the machine.

## Running a Training Job

1. Define your training job in a YAML file.
```bash
cp config_template.yaml my_job.yaml
nano my_job.yaml
```

2. Execute the CLI, pointing it to your config:
```bash
python3 -m forgelm.cli --config my_job.yaml
# or (after editable install):
forgelm --config my_job.yaml
```

## Webhook Notifications (Optional)

If you want notifications on start/success/failure, configure `webhook:` in your YAML. For CI/CD, prefer secrets via env vars:

```bash
export FORGELM_WEBHOOK_URL="https://hooks.slack.com/services/XXX/YYY/ZZZ"
```

And in `my_job.yaml`:

```yaml
webhook:
  url_env: "FORGELM_WEBHOOK_URL"
  notify_on_start: true
  notify_on_success: true
  notify_on_failure: true
```

## Logs and Outputs

As the job runs, ForgeLM will print configuration states, dataset shapes, and LoRA trainable parameter percentages directly to stdout.

Hugging Face Trainer will log metrics (Training Loss, Validation Loss) to the console and to **TensorBoard**.

You can view live graphs during training by opening a new terminal tab and running:
```bash
tensorboard --logdir=./checkpoints/runs/
```

### Final Artifacts
When training successfully finishes:
1. The final model/adapters and the tokenizer will be saved under `training.output_dir/training.final_model_dir` (defaults to `./checkpoints/final_model/`).
2. Intermediate checkpoints remain in `training.output_dir` depending on your `save_total_limit` parameter in the config.

By default, ForgeLM saves **adapter-only** artifacts (LoRA) to keep outputs small and to make Phase 2 auto-revert safe. If you want a merged full model, set:

```yaml
training:
  merge_adapters: true
```
