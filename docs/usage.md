# Usage Guide

ForgeLM is designed to be executed via a command-line interface, making it perfect for both local experimentation and remote GPU execution (RunPod, Lambda Labs, AWS).

## Prerequisites

Ensure you have a machine with an NVIDIA GPU and CUDA installed. While ForgeLM will attempt to operate in CPU mode, training LLMs effectively requires a GPU.

```bash
git clone https://github.com/cemililik/ForgeLM.git
cd ForgeLM
pip install -r requirements.txt
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
python -m forgelm.cli --config my_job.yaml
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
1. The final, merged weights (or LoRA adapters) and the modified tokenizer will be saved to `./final_model/`.
2. Intermediate checkpoints remain in `./checkpoints/` depending on your `save_total_limit` parameter in the config.
