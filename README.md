# ForgeLM

**ForgeLM** is an enhanced, enterprise-ready Language Model Fine-Tuning Toolkit with LoRA support and advanced features. It's designed to make building your own specialized LLMs simple, modular, and easy to integrate into automated pipelines.

## Features
- **Modular Architecture**: Separate modules for data processing, model loading, and training orchestration.
- **LoRA Support**: Easily configure and integrate Low-Rank Adaptation (LoRA) for efficient fine-tuning.
- **Config-Driven**: Run training jobs effortlessly using YAML configuration files.
- **CLI / Automation Ready**: Perfect for CI/CD or local automated runs. No necessary interactive prompts if a config is provided.
- **Checkpoint Management**: Automatically handle saving, keeping, or compressing checkpoints.

## Documentation
For detailed guides on how to use ForgeLM, please see our dedicated documentations:
1. [Architecture Overview](docs/architecture.md) (🇹🇷 [Türkçe](docs/architecture-tr.md))
2. [Configuration Guide](docs/configuration.md) (🇹🇷 [Türkçe](docs/configuration-tr.md))
3. [Usage & Execution](docs/usage.md) (🇹🇷 [Türkçe](docs/usage-tr.md))
4. [Data Preparation Format](docs/data_preparation.md) (🇹🇷 [Türkçe](docs/data_preparation-tr.md))

## Installation

```bash
git clone https://github.com/cemililik/ForgeLM.git
cd ForgeLM
pip install -r requirements.txt
```

## Quick Start

1. Generate or copy the configuration template:
```bash
cp config_template.yaml my_config.yaml
```

2. Edit `my_config.yaml` with your model repository, dataset, and training parameters.

3. Start training:
```bash
python -m forgelm.cli --config my_config.yaml
```

## Directory Structure
- `forgelm/`: The core Python package.
  - `config.py`: Configuration parsing and validation using Pydantic.
  - `data.py`: Dataset loading, tokenizing, and preprocessing.
  - `model.py`: Model loading and PEFT/LoRA preparation.
  - `trainer.py`: Fine-tuning orchestration loop.
  - `utils.py`: Authentication, logging, and checkpoint management.
  - `cli.py`: Command Line Interface.
