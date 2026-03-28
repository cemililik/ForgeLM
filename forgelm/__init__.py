"""
ForgeLM package.

Keep imports lightweight so `python -m forgelm.cli --help` and config parsing work
without requiring heavy ML dependencies (torch/transformers).
"""

from .config import ConfigError, ForgeConfig, load_config

__version__ = "0.3.0"

__all__ = [
    "load_config",
    "ForgeConfig",
    "ConfigError",
    "prepare_dataset",
    "get_model_and_tokenizer",
    "ForgeTrainer",
    "TrainResult",
    "setup_authentication",
    "manage_checkpoints",
    "run_benchmark",
    "BenchmarkResult",
    "SyntheticDataGenerator",
]


def __getattr__(name: str):
    # Lazy imports to avoid pulling heavy deps unless needed.
    if name == "prepare_dataset":
        from .data import prepare_dataset as v

        return v
    if name == "get_model_and_tokenizer":
        from .model import get_model_and_tokenizer as v

        return v
    if name == "ForgeTrainer":
        from .trainer import ForgeTrainer as v

        return v
    if name == "TrainResult":
        from .results import TrainResult as v

        return v
    if name == "run_benchmark":
        from .benchmark import run_benchmark as v

        return v
    if name == "BenchmarkResult":
        from .benchmark import BenchmarkResult as v

        return v
    if name == "setup_authentication":
        from .utils import setup_authentication as v

        return v
    if name == "manage_checkpoints":
        from .utils import manage_checkpoints as v

        return v
    if name == "SyntheticDataGenerator":
        from .synthetic import SyntheticDataGenerator as v

        return v
    raise AttributeError(name)
