"""
ForgeLM package.

Keep imports lightweight so `python -m forgelm.cli --help` and config parsing work
without requiring heavy ML dependencies (torch/transformers).
"""

from .config import load_config, ForgeConfig

__all__ = ["load_config", "ForgeConfig", "prepare_dataset", "get_model_and_tokenizer", "ForgeTrainer", "setup_authentication", "manage_checkpoints"]


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
    if name == "setup_authentication":
        from .utils import setup_authentication as v
        return v
    if name == "manage_checkpoints":
        from .utils import manage_checkpoints as v
        return v
    raise AttributeError(name)
