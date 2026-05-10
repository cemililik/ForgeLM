"""Tests for SFT ``SFTConfig`` kwarg construction across trl versions.

Regression guard: trl 0.13 renamed the sequence-length cap from
``max_seq_length`` to ``max_length`` on ``SFTConfig`` and removed the old
name. Passing the old kwarg raises ``TypeError`` at trainer args build
time and aborts training on every modern trl install.

``pyproject.toml`` pins ``trl>=0.12.0,<2.0.0``, so the trainer must
detect at runtime which parameter the installed ``SFTConfig`` accepts.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

torch_available = True
try:
    import torch  # noqa: F401
except ImportError:
    torch_available = False


def _make_sft_config(tmp_path):
    from forgelm.config import ForgeConfig

    return ForgeConfig(
        **{
            "model": {"name_or_path": "org/model", "max_length": 2048},
            "lora": {},
            "training": {
                "trainer_type": "sft",
                "output_dir": str(tmp_path),
            },
            "data": {"dataset_name_or_path": "org/dataset"},
        }
    )


def _seed_trainer(tmp_path):
    """Build a bare trainer skeleton without invoking heavy init."""
    from forgelm.trainer import ForgeTrainer

    config = _make_sft_config(tmp_path)
    trainer = ForgeTrainer.__new__(ForgeTrainer)
    trainer.model = MagicMock()
    trainer.tokenizer = MagicMock()
    trainer.config = config
    trainer.dataset = {"train": list(range(10))}
    trainer.checkpoint_dir = str(tmp_path)
    trainer.run_name = "sft_kwarg_test"
    trainer.notifier = MagicMock()
    trainer.audit = MagicMock()
    return trainer


@pytest.mark.skipif(not torch_available, reason="torch not installed")
def test_sft_config_uses_max_length_on_modern_trl(tmp_path):
    """trl 0.13+ removed ``max_seq_length``; the trainer must use
    ``max_length`` instead."""

    captured_kwargs: dict = {}

    class FakeModernSFTConfig:
        def __init__(self, *, max_length=None, packing=False, dataset_text_field=None, **other):
            captured_kwargs["max_length"] = max_length
            captured_kwargs["packing"] = packing
            captured_kwargs["dataset_text_field"] = dataset_text_field
            captured_kwargs.update(other)

    trainer = _seed_trainer(tmp_path)

    with patch("trl.SFTConfig", FakeModernSFTConfig):
        trainer._get_training_args_for_type()

    assert captured_kwargs["max_length"] == 2048, (
        "Modern trl `SFTConfig(max_length=...)` must receive the model's "
        f"max_length (got: {captured_kwargs.get('max_length')!r})"
    )
    assert "max_seq_length" not in captured_kwargs, (
        "Legacy `max_seq_length` kwarg must NOT be passed to a modern SFTConfig — trl 0.13+ raises TypeError on it."
    )
    assert captured_kwargs["dataset_text_field"] == "text"


@pytest.mark.skipif(not torch_available, reason="torch not installed")
def test_sft_config_uses_max_seq_length_on_legacy_trl(tmp_path):
    """trl 0.12.x: ``SFTConfig`` accepts ``max_seq_length`` only. The
    trainer must fall back to that name when the modern ``max_length``
    parameter is unavailable."""

    captured_kwargs: dict = {}

    class FakeLegacySFTConfig:
        def __init__(self, *, max_seq_length=None, packing=False, dataset_text_field=None, **other):
            captured_kwargs["max_seq_length"] = max_seq_length
            captured_kwargs["packing"] = packing
            captured_kwargs["dataset_text_field"] = dataset_text_field
            captured_kwargs.update(other)

    trainer = _seed_trainer(tmp_path)

    with patch("trl.SFTConfig", FakeLegacySFTConfig):
        trainer._get_training_args_for_type()

    assert captured_kwargs["max_seq_length"] == 2048
    assert "max_length" not in captured_kwargs, (
        "Modern `max_length` kwarg must NOT be passed to legacy trl 0.12.x SFTConfig."
    )


@pytest.mark.skipif(not torch_available, reason="torch not installed")
def test_sft_config_passes_packing_and_dataset_text_field(tmp_path):
    """Regression: ``packing`` and ``dataset_text_field`` must keep being
    propagated alongside the sequence-length cap."""

    captured_kwargs: dict = {}

    class FakeSFTConfig:
        def __init__(self, *, max_length=None, packing=False, dataset_text_field=None, **other):
            captured_kwargs["max_length"] = max_length
            captured_kwargs["packing"] = packing
            captured_kwargs["dataset_text_field"] = dataset_text_field

    trainer = _seed_trainer(tmp_path)
    trainer.config.training.packing = True

    with patch("trl.SFTConfig", FakeSFTConfig):
        trainer._get_training_args_for_type()

    assert captured_kwargs["packing"] is True
    assert captured_kwargs["dataset_text_field"] == "text"
