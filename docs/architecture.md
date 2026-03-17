# ForgeLM Architecture

ForgeLM is designed with modularity and extensibility in mind. Instead of a monolithic script, the workflow is broken down into distinct stages.

## System Overview

The application is structured into a Python package under `forgelm/` with a CLI entrypoint. At its core, it loads a configuration, prepares the dataset, initializes the model with LoRA bounds, and hands the process off to the Trainer.

### Directory Layout

```
ForgeLM/
├── forgelm/               # Core Python Package
│   ├── __init__.py        # Exposes main entrypoints
│   ├── cli.py             # Command Line Interface (Argparse)
│   ├── config.py          # Configuration schema (Pydantic)
│   ├── data.py            # HF Datasets loading and tokenization
│   ├── model.py           # HF Transformers and PEFT model setup
│   ├── trainer.py         # HF Trainer abstraction
│   └── utils.py           # Helpers (Auth, Checkpoint Mgmt)
├── docs/                  # Project Documentation
├── config_template.yaml   # Base configuration for users
├── requirements.txt       # Python dependencies
└── README.md              # Project root documentation
```

## Component Details

### 1. `config.py`
We use `pydantic` to define nested data models (`ModelConfig`, `LoraConfigModel`, `TrainingConfig`, `DataConfig`, `AuthConfig`).
This ensures that any YAML file provided to the CLI is immediately validated. If a user provides an invalid type (e.g., a string for `learning_rate`), Pydantic will raise a clean error before any heavy models are loaded.

### 2. `data.py`
This module interfaces with the `datasets` library. It contains logic to:
- Load local files or Hugging Face hub datasets.
- Ensure a validation split exists (creating a 10% slice if necessary).
- Format system, user, and assistant prompts into a cohesive string.
- Tokenize the strings and correctly mask padding tokens in the Labels array to prevent the model from learning padding.

### 3. `model.py`
This module sets up the Hugging Face `AutoModelForCausalLM`. Crucially, it detects if a GPU is available (`torch.cuda.is_available()`) and injects `bitsandbytes` 8-bit quantization (`load_in_8bit=True`). Afterward, it wraps the model with `peft` based on the user's LoRA configuration to prepare for parameter-efficient fine-tuning.

### 4. `trainer.py`
Provides the `ForgeTrainer` wrapper around Hugging Face's `SFTTrainer` or standard `Trainer`. It handles mapping the configuration outputs directly into `TrainingArguments`.

### 5. `utils.py`
Handles Hugging Face Hub `login()` functions, preferring explicit tokens mapped in the config, falling back to OS Environment Variables, and finally falling back to `~/.huggingface/token`. Also contains the checkpoint zipping/deletion logic.

### 6. `cli.py`
The orchestrator. It sequentially calls components: Config -> Auth -> Model/Tokenizer -> Data -> Trainer -> Save/Cleanup.
