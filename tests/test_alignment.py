"""Unit tests for Phase 5 alignment trainer support (DPO, SimPO, KTO, GRPO)."""

import pytest
import yaml

from forgelm.config import ForgeConfig, TrainingConfig, load_config

# --- TrainingConfig trainer_type ---


class TestTrainerTypeConfig:
    def test_default_is_sft(self):
        t = TrainingConfig()
        assert t.trainer_type == "sft"

    def test_all_valid_types(self, minimal_config):
        for tt in ["sft", "orpo", "dpo", "simpo", "kto", "grpo"]:
            cfg = ForgeConfig(**minimal_config(training={"trainer_type": tt}))
            assert cfg.training.trainer_type == tt

    def test_invalid_trainer_type_raises(self, minimal_config):
        with pytest.raises((ValueError, TypeError)):
            ForgeConfig(**minimal_config(training={"trainer_type": "invalid"}))

    def test_dpo_parameters(self):
        t = TrainingConfig(trainer_type="dpo", dpo_beta=0.2)
        assert t.dpo_beta == pytest.approx(0.2)

    def test_simpo_parameters(self):
        t = TrainingConfig(trainer_type="simpo", simpo_gamma=1.0, simpo_beta=3.0)
        assert t.simpo_gamma == pytest.approx(1.0)
        assert t.simpo_beta == pytest.approx(3.0)

    def test_kto_parameters(self):
        t = TrainingConfig(trainer_type="kto", kto_beta=0.05)
        assert t.kto_beta == pytest.approx(0.05)

    def test_grpo_parameters(self):
        # Legacy alias `grpo_max_new_tokens` must still be accepted on input;
        # the canonical attribute is `grpo_max_completion_length` (matches TRL).
        t = TrainingConfig(
            trainer_type="grpo",
            grpo_num_generations=8,
            grpo_max_new_tokens=1024,
        )
        assert t.grpo_num_generations == 8
        assert t.grpo_max_completion_length == 1024

    def test_grpo_defaults(self):
        t = TrainingConfig(trainer_type="grpo")
        assert t.grpo_num_generations == 4
        assert t.grpo_max_completion_length == 512


# --- Full config with alignment ---


class TestAlignmentFullConfig:
    def test_dpo_config_from_yaml(self, tmp_path, minimal_config):
        data = minimal_config(
            training={
                "trainer_type": "dpo",
                "dpo_beta": 0.15,
                "learning_rate": 5e-6,
            }
        )
        cfg_path = str(tmp_path / "config.yaml")
        with open(cfg_path, "w") as f:
            yaml.dump(data, f)
        cfg = load_config(cfg_path)
        assert cfg.training.trainer_type == "dpo"
        assert cfg.training.dpo_beta == pytest.approx(0.15)

    def test_simpo_config_from_yaml(self, tmp_path, minimal_config):
        data = minimal_config(
            training={
                "trainer_type": "simpo",
                "simpo_gamma": 0.8,
            }
        )
        cfg_path = str(tmp_path / "config.yaml")
        with open(cfg_path, "w") as f:
            yaml.dump(data, f)
        cfg = load_config(cfg_path)
        assert cfg.training.trainer_type == "simpo"
        assert cfg.training.simpo_gamma == pytest.approx(0.8)

    def test_grpo_config_from_yaml(self, tmp_path, minimal_config):
        data = minimal_config(
            training={
                "trainer_type": "grpo",
                "grpo_num_generations": 6,
                "grpo_max_new_tokens": 256,
            }
        )
        cfg_path = str(tmp_path / "config.yaml")
        with open(cfg_path, "w") as f:
            yaml.dump(data, f)
        cfg = load_config(cfg_path)
        assert cfg.training.trainer_type == "grpo"
        assert cfg.training.grpo_num_generations == 6


# --- Dry-run with alignment trainers ---


class TestDryRunAlignment:
    def test_dry_run_shows_trainer_type(self, capsys, minimal_config):
        from forgelm.cli import _run_dry_run

        cfg = ForgeConfig(**minimal_config(training={"trainer_type": "dpo"}))
        _run_dry_run(cfg, "json")
        import json

        result = json.loads(capsys.readouterr().out)
        assert result["status"] == "valid"

    def test_dry_run_grpo(self, capsys, minimal_config):
        from forgelm.cli import _run_dry_run

        cfg = ForgeConfig(**minimal_config(training={"trainer_type": "grpo"}))
        _run_dry_run(cfg, "json")
        import json

        result = json.loads(capsys.readouterr().out)
        assert result["status"] == "valid"


# --- Config template ---


class TestConfigTemplateAlignment:
    def test_config_template_still_valid(self):
        """Ensure config_template.yaml still parses after alignment changes."""
        import os

        template_path = os.path.join(os.path.dirname(__file__), "..", "config_template.yaml")
        if os.path.exists(template_path):
            cfg = load_config(template_path)
            assert cfg.training.trainer_type == "sft"
