"""Tests for GaLore (Gradient Low-Rank Projection) integration."""

import json

import pytest

from forgelm.config import ForgeConfig, load_config

# Minimal required fields for ForgeConfig
BASE = {
    "model": {"name_or_path": "test/model"},
    "lora": {"r": 16, "alpha": 32},
    "data": {"dataset_name_or_path": "test.jsonl"},
}


def _config(**overrides):
    """Create a ForgeConfig with minimal defaults + overrides."""
    cfg = {**BASE, "training": {"output_dir": "./out"}}
    for key, val in overrides.items():
        if key == "training":
            cfg["training"].update(val)
        else:
            cfg[key] = val
    return ForgeConfig(**cfg)


class TestGaloreConfig:
    """Test GaLore configuration in TrainingConfig."""

    def test_galore_disabled_by_default(self):
        config = _config()
        assert config.training.galore_enabled is False

    def test_galore_enabled(self):
        config = _config(
            training={
                "galore_enabled": True,
                "galore_rank": 64,
                "galore_update_proj_gap": 100,
                "galore_scale": 0.10,
            }
        )
        assert config.training.galore_enabled is True
        assert config.training.galore_rank == 64
        assert config.training.galore_update_proj_gap == 100
        assert config.training.galore_scale == pytest.approx(0.10)

    def test_galore_defaults(self):
        config = _config(training={"galore_enabled": True})
        assert config.training.galore_optim == "galore_adamw"
        assert config.training.galore_rank == 128
        assert config.training.galore_update_proj_gap == 200
        assert config.training.galore_scale == pytest.approx(0.25)
        assert config.training.galore_proj_type == "std"
        assert config.training.galore_target_modules is None

    def test_galore_all_optim_variants(self):
        valid_optims = [
            "galore_adamw",
            "galore_adamw_8bit",
            "galore_adafactor",
            "galore_adamw_layerwise",
            "galore_adamw_8bit_layerwise",
            "galore_adafactor_layerwise",
        ]
        for optim in valid_optims:
            config = _config(training={"galore_enabled": True, "galore_optim": optim})
            assert config.training.galore_optim == optim

    def test_galore_invalid_optim_raises(self):
        with pytest.raises(ValueError, match="galore_optim"):
            _config(training={"galore_enabled": True, "galore_optim": "invalid_optim"})

    def test_galore_with_lora_is_valid(self):
        """GaLore + LoRA is unusual but valid — just logs a warning."""
        config = _config(training={"galore_enabled": True})
        assert config.training.galore_enabled is True
        assert config.lora.r == 16

    def test_galore_layerwise_with_distributed_raises(self):
        with pytest.raises(ValueError, match="layerwise.*multi-GPU"):
            _config(
                training={"galore_enabled": True, "galore_optim": "galore_adamw_layerwise"},
                distributed={"strategy": "deepspeed"},
            )

    def test_galore_non_layerwise_with_distributed_ok(self):
        config = _config(
            training={"galore_enabled": True, "galore_optim": "galore_adamw"},
            distributed={"strategy": "deepspeed"},
        )
        assert config.training.galore_enabled is True
        assert config.distributed.strategy == "deepspeed"

    def test_galore_custom_target_modules(self):
        config = _config(
            training={
                "galore_enabled": True,
                "galore_target_modules": [r".*.q_proj", r".*.v_proj"],
            }
        )
        assert config.training.galore_target_modules == [r".*.q_proj", r".*.v_proj"]

    def test_galore_proj_types(self):
        for proj_type in ["std", "reverse_std", "right", "left", "full"]:
            config = _config(training={"galore_enabled": True, "galore_proj_type": proj_type})
            assert config.training.galore_proj_type == proj_type


class TestGaloreYaml:
    """Test GaLore config loading from YAML."""

    def test_galore_yaml_round_trip(self, tmp_path):
        yaml_content = """
model:
  name_or_path: "test/model"
lora:
  r: 16
  alpha: 32
data:
  dataset_name_or_path: "test.jsonl"
training:
  output_dir: "./out"
  galore_enabled: true
  galore_optim: "galore_adamw_8bit"
  galore_rank: 64
  galore_update_proj_gap: 100
  galore_scale: 0.10
  galore_proj_type: "std"
"""
        config_file = tmp_path / "galore.yaml"
        config_file.write_text(yaml_content)

        config = load_config(str(config_file))
        assert config.training.galore_enabled is True
        assert config.training.galore_optim == "galore_adamw_8bit"
        assert config.training.galore_rank == 64
        assert config.training.galore_update_proj_gap == 100
        assert config.training.galore_scale == pytest.approx(0.10)

    def test_config_template_still_valid(self):
        config = load_config("config_template.yaml")
        assert config.training.galore_enabled is False


class TestGaloreDryRun:
    """Test GaLore in dry-run output."""

    def test_dry_run_json_shows_galore(self, tmp_path):
        from forgelm.cli import _run_dry_run

        yaml_content = """
model:
  name_or_path: "test/model"
lora:
  r: 16
  alpha: 32
data:
  dataset_name_or_path: "test.jsonl"
training:
  output_dir: "./out"
  galore_enabled: true
  galore_optim: "galore_adamw_8bit"
  galore_rank: 64
"""
        config_file = tmp_path / "galore.yaml"
        config_file.write_text(yaml_content)
        config = load_config(str(config_file))

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            _run_dry_run(config, output_format="json")
        output = json.loads(f.getvalue())

        assert output["galore_enabled"] is True
        assert output["galore_optim"] == "galore_adamw_8bit"
        assert output["galore_rank"] == 64

    def test_dry_run_json_no_galore(self, tmp_path):
        from forgelm.cli import _run_dry_run

        yaml_content = """
model:
  name_or_path: "test/model"
lora:
  r: 16
  alpha: 32
data:
  dataset_name_or_path: "test.jsonl"
training:
  output_dir: "./out"
"""
        config_file = tmp_path / "galore.yaml"
        config_file.write_text(yaml_content)
        config = load_config(str(config_file))

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            _run_dry_run(config, output_format="json")
        output = json.loads(f.getvalue())

        assert output["galore_enabled"] is False
        assert output["galore_optim"] is None
