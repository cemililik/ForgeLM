"""Tests for GRPO ``GRPOConfig`` kwarg construction and the legacy alias.

Two regressions guarded here:

1. TRL >=0.12 renamed the per-completion token cap from ``max_new_tokens`` to
   ``max_completion_length`` on ``GRPOConfig``. Passing the old kwarg raises
   ``TypeError`` at trainer args build time and aborts training. We verify the
   trainer wires the new name and does NOT wire the old one.
2. The Pydantic field was renamed from ``grpo_max_new_tokens`` to
   ``grpo_max_completion_length``. The legacy field name must keep working as
   an input alias so existing user YAML configs and the bundled templates
   keep loading without edits.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

# Same probe pattern as tests/test_grpo_reward.py: trl's GRPO module is
# lazy-loaded and can fail to import on certain torch/trl version pairings.
torch_available = True
try:
    import torch  # noqa: F401
except ImportError:
    torch_available = False

grpo_patchable = False
if torch_available:
    try:
        import trl  # noqa: F401

        trl.GRPOTrainer  # noqa: B018
        grpo_patchable = True
    except (ImportError, AttributeError, RuntimeError):
        grpo_patchable = False


def _make_grpo_config(tmp_path):
    from forgelm.config import ForgeConfig

    return ForgeConfig(
        **{
            "model": {"name_or_path": "org/model"},
            "lora": {},
            "training": {
                "trainer_type": "grpo",
                "output_dir": str(tmp_path),
                "grpo_max_completion_length": 256,
            },
            "data": {"dataset_name_or_path": "org/dataset"},
        }
    )


@pytest.mark.skipif(not torch_available, reason="torch not installed")
@pytest.mark.skipif(
    not grpo_patchable,
    reason="trl.GRPOTrainer not importable in this environment",
)
def test_grpo_config_uses_max_completion_length(tmp_path):
    """``_get_training_args_for_type`` must pass ``max_completion_length`` (not
    the legacy ``max_new_tokens``) to ``GRPOConfig``."""
    from forgelm.trainer import ForgeTrainer

    config = _make_grpo_config(tmp_path)

    trainer = ForgeTrainer.__new__(ForgeTrainer)
    trainer.model = MagicMock()
    trainer.tokenizer = MagicMock()
    trainer.config = config
    trainer.dataset = {"train": list(range(10))}
    trainer.checkpoint_dir = str(tmp_path)
    trainer.run_name = "grpo_kwarg_test"
    trainer.notifier = MagicMock()
    trainer.audit = MagicMock()

    captured_kwargs: dict = {}

    def fake_grpo_config(**kwargs):
        captured_kwargs.update(kwargs)
        return MagicMock()

    with patch("trl.GRPOConfig", side_effect=fake_grpo_config):
        trainer._get_training_args_for_type()

    assert "max_completion_length" in captured_kwargs, (
        "GRPOConfig must receive `max_completion_length` (TRL >=0.12 field name); "
        f"got kwargs: {sorted(captured_kwargs)}"
    )
    assert captured_kwargs["max_completion_length"] == 256
    assert "max_new_tokens" not in captured_kwargs, (
        "Legacy `max_new_tokens` kwarg must NOT be passed to GRPOConfig — TRL >=0.12 raises TypeError on it."
    )


def test_legacy_field_name_still_accepted(tmp_path):
    """Existing YAML configs using the legacy ``grpo_max_new_tokens`` key must
    still load — Pydantic alias keeps the old field name working."""
    import yaml

    from forgelm.config import load_config

    yaml_data = {
        "model": {"name_or_path": "org/model"},
        "lora": {},
        "training": {
            "trainer_type": "grpo",
            "output_dir": str(tmp_path / "out"),
            "grpo_max_new_tokens": 256,  # legacy field name
        },
        "data": {"dataset_name_or_path": "org/dataset"},
    }
    cfg_path = tmp_path / "config.yaml"
    with open(cfg_path, "w") as f:
        yaml.dump(yaml_data, f)

    cfg = load_config(str(cfg_path))
    assert cfg.training.grpo_max_completion_length == 256, (
        "Legacy `grpo_max_new_tokens` YAML key must populate the renamed "
        "`grpo_max_completion_length` attribute via Pydantic alias."
    )


def test_canonical_field_name_works(tmp_path):
    """The new canonical name ``grpo_max_completion_length`` must also work."""
    import yaml

    from forgelm.config import load_config

    yaml_data = {
        "model": {"name_or_path": "org/model"},
        "lora": {},
        "training": {
            "trainer_type": "grpo",
            "output_dir": str(tmp_path / "out"),
            "grpo_max_completion_length": 384,
        },
        "data": {"dataset_name_or_path": "org/dataset"},
    }
    cfg_path = tmp_path / "config.yaml"
    with open(cfg_path, "w") as f:
        yaml.dump(yaml_data, f)

    cfg = load_config(str(cfg_path))
    assert cfg.training.grpo_max_completion_length == 384
