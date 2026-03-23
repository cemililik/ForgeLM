# ForgeLM

**ForgeLM** is an enhanced, enterprise-ready Language Model Fine-Tuning Toolkit with LoRA support and advanced features. It's designed to make building your own specialized LLMs simple, modular, and easy to integrate into automated pipelines.

## Features
- **Unsloth & Transformers**: Train blazingly fast with the `unsloth` backend, or fall back to standard `transformers` automatically.
- **4-Bit QLoRA & DoRA**: State-of-the-Art parameter-efficient fine-tuning utilizing NF4 quantization and Weight-Decomposed LoRA for massive memory savings.
- **ORPO Preference Alignment**: Single-stage SFT + preference alignment using `chosen`/`rejected` datasets.
- **Dynamic Chat Templates**: Datasets are automatically formatted to match your base model's native conversational structure (e.g. `<|im_start|>`) via `tokenizer.apply_chat_template`.
- **Config-Driven**: Run training jobs effortlessly using declarative YAML files—built for CI/CD and MLOps automation.
- **Automated Benchmarking**: Post-training evaluation via `lm-evaluation-harness` with configurable tasks and auto-revert.
- **Checkpoint Management**: Automatically handle saving, early stopping, checkpoint resume, and disk cleanup.
- **Docker Support**: Official Dockerfile and docker-compose for portable, single-command training.
- **Multi-Dataset Training**: Mix multiple datasets with configurable ratios in a single training run.
- **Model Card Generation**: Automatic HF-compatible model cards with training config, metrics, and benchmarks.
- **W&B / MLflow / TensorBoard**: Flexible experiment tracking via `report_to` config parameter.

## Documentation
For detailed guides on how to use ForgeLM, please see our dedicated documentations:
1. [Architecture Overview](docs/architecture.md) ([Türkçe](docs/architecture-tr.md))
2. [Configuration Guide](docs/configuration.md) ([Türkçe](docs/configuration-tr.md))
3. [Usage & Execution](docs/usage.md) ([Türkçe](docs/usage-tr.md))
4. [Data Preparation Format](docs/data_preparation.md) ([Türkçe](docs/data_preparation-tr.md))
5. [Distributed Training (Multi-GPU)](docs/distributed_training.md) ([Türkçe](docs/distributed_training-tr.md))
6. [Product Strategy](docs/product_strategy.md) ([Türkçe](docs/product_strategy-tr.md))
7. [Roadmap](docs/roadmap.md) ([Türkçe](docs/roadmap-tr.md))

## Installation

```bash
git clone https://github.com/cemililik/ForgeLM.git
cd ForgeLM
python3 -m pip install -e .
```

### Optional installs (recommended)

- **Enable QLoRA dependencies (Linux)**:

```bash
python3 -m pip install -e ".[qlora]"
```

- **Enable Unsloth backend (Linux)**:

```bash
python3 -m pip install -e ".[unsloth]"
```

- **Evaluation / Benchmark**:

```bash
python3 -m pip install -e ".[eval]"
```

### Alternative (requirements files)

If you prefer a requirements-based install (e.g., CI/CD images), you can use:

- Core:

```bash
python3 -m pip install -r requirements.txt
```

- Linux speedups:

```bash
python3 -m pip install -r requirements-linux.txt
```

- Evaluation harness:

```bash
python3 -m pip install -r requirements-eval.txt
```

- **Install as a package (CLI `forgelm`)**:

```bash
python3 -m pip install -e .
```

## Quick Start

1. Generate or copy the configuration template:
```bash
cp config_template.yaml my_config.yaml
```

2. Edit `my_config.yaml` with your model repository, dataset, and training parameters.

3. Start training:
```bash
forgelm --config my_config.yaml
```

Or use the interactive wizard to generate a config:
```bash
forgelm --wizard
```

## Docker

```bash
# Build
docker build -t forgelm .

# Run training
docker run --gpus all \
  -v $(pwd)/my_config.yaml:/workspace/config.yaml \
  -v $(pwd)/output:/workspace/output \
  forgelm --config /workspace/config.yaml

# Dry-run
docker run forgelm --config /workspace/config.yaml --dry-run --output-format json
```

## Directory Structure
- `forgelm/`: The core Python package.
  - `config.py`: Configuration parsing and validation using Pydantic.
  - `data.py`: Dataset loading, tokenizing, and preprocessing.
  - `model.py`: Model loading and PEFT/LoRA preparation.
  - `trainer.py`: Fine-tuning orchestration loop (SFT & ORPO).
  - `benchmark.py`: Post-training evaluation via lm-evaluation-harness.
  - `model_card.py`: Automatic model card generation.
  - `wizard.py`: Interactive configuration wizard.
  - `webhook.py`: Webhook notifications (Slack/Teams/generic).
  - `utils.py`: Authentication, logging, and checkpoint management.
  - `cli.py`: Command Line Interface.
