# ForgeLM

**ForgeLM** is an enhanced, enterprise-ready Language Model Fine-Tuning Toolkit with LoRA support and advanced features. It's designed to make building your own specialized LLMs simple, modular, and easy to integrate into automated pipelines.

## Features
- **Unsloth & Transformers**: Train blazingly fast with the `unsloth` backend, or fall back to standard `transformers` automatically.
- **4-Bit QLoRA & DoRA**: State-of-the-Art parameter-efficient fine-tuning utilizing NF4 quantization and Weight-Decomposed LoRA for massive memory savings.
- **Dynamic Chat Templates**: Datasets are automatically formatted to match your base model's native conversational structure (e.g. `<|im_start|>`) via `tokenizer.apply_chat_template`.
- **Config-Driven**: Run training jobs effortlessly using declarative YAML files—built for CI/CD and MLOps automation.
- **Checkpoint Management**: Automatically handle saving, early stopping, and disk cleanup.

## Documentation
For detailed guides on how to use ForgeLM, please see our dedicated documentations:
1. [Architecture Overview](docs/architecture.md) ([Türkçe](docs/architecture-tr.md))
2. [Configuration Guide](docs/configuration.md) ([Türkçe](docs/configuration-tr.md))
3. [Usage & Execution](docs/usage.md) ([Türkçe](docs/usage-tr.md))
4. [Data Preparation Format](docs/data_preparation.md) ([Türkçe](docs/data_preparation-tr.md))

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
