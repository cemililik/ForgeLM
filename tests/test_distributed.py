"""Unit tests for distributed training configuration (DeepSpeed/FSDP)."""

import json
import os

import yaml

from forgelm.config import (
    DistributedConfig,
    ForgeConfig,
    load_config,
)


def _minimal_config(**overrides):
    data = {
        "model": {"name_or_path": "org/model"},
        "lora": {},
        "training": {},
        "data": {"dataset_name_or_path": "org/dataset"},
    }
    data.update(overrides)
    return data


# --- DistributedConfig ---


class TestDistributedConfig:
    def test_defaults(self):
        d = DistributedConfig()
        assert d.strategy is None
        assert d.deepspeed_config is None
        assert d.fsdp_strategy == "full_shard"
        assert d.fsdp_auto_wrap is True
        assert d.fsdp_offload is False

    def test_deepspeed_strategy(self):
        d = DistributedConfig(strategy="deepspeed", deepspeed_config="zero2")
        assert d.strategy == "deepspeed"
        assert d.deepspeed_config == "zero2"

    def test_fsdp_strategy(self):
        d = DistributedConfig(strategy="fsdp", fsdp_strategy="shard_grad_op")
        assert d.strategy == "fsdp"
        assert d.fsdp_strategy == "shard_grad_op"

    def test_fsdp_with_offload(self):
        d = DistributedConfig(strategy="fsdp", fsdp_offload=True)
        assert d.fsdp_offload is True


# --- ForgeConfig with distributed ---


class TestForgeConfigDistributed:
    def test_no_distributed(self):
        cfg = ForgeConfig(**_minimal_config())
        assert cfg.distributed is None

    def test_deepspeed_config(self):
        cfg = ForgeConfig(**_minimal_config(distributed={"strategy": "deepspeed", "deepspeed_config": "zero3"}))
        assert cfg.distributed.strategy == "deepspeed"
        assert cfg.distributed.deepspeed_config == "zero3"

    def test_fsdp_config(self):
        cfg = ForgeConfig(**_minimal_config(distributed={"strategy": "fsdp", "fsdp_strategy": "hybrid_shard"}))
        assert cfg.distributed.strategy == "fsdp"
        assert cfg.distributed.fsdp_strategy == "hybrid_shard"

    def test_unsloth_distributed_warning(self, caplog):
        """Unsloth + distributed should produce a warning."""
        import logging

        with caplog.at_level(logging.WARNING, logger="forgelm.config"):
            ForgeConfig(
                **_minimal_config(
                    model={"name_or_path": "org/model", "backend": "unsloth"},
                    distributed={"strategy": "deepspeed"},
                )
            )
        assert "Unsloth backend does not support multi-GPU" in caplog.text

    def test_zero3_qlora_warning(self, caplog):
        """QLoRA + ZeRO-3 should produce a warning."""
        import logging

        with caplog.at_level(logging.WARNING, logger="forgelm.config"):
            ForgeConfig(
                **_minimal_config(
                    model={"name_or_path": "org/model", "load_in_4bit": True},
                    distributed={"strategy": "deepspeed", "deepspeed_config": "zero3"},
                )
            )
        assert "QLoRA (4-bit) with DeepSpeed ZeRO-3" in caplog.text

    def test_zero2_qlora_no_warning(self, caplog):
        """QLoRA + ZeRO-2 should NOT produce the ZeRO-3 warning."""
        import logging

        with caplog.at_level(logging.WARNING, logger="forgelm.config"):
            ForgeConfig(
                **_minimal_config(
                    model={"name_or_path": "org/model", "load_in_4bit": True},
                    distributed={"strategy": "deepspeed", "deepspeed_config": "zero2"},
                )
            )
        assert "QLoRA (4-bit) with DeepSpeed ZeRO-3" not in caplog.text


# --- YAML load with distributed ---


class TestLoadConfigDistributed:
    def test_load_deepspeed_yaml(self, tmp_path):
        data = _minimal_config(distributed={"strategy": "deepspeed", "deepspeed_config": "zero2"})
        cfg_path = str(tmp_path / "config.yaml")
        with open(cfg_path, "w") as f:
            yaml.dump(data, f)
        cfg = load_config(cfg_path)
        assert cfg.distributed.strategy == "deepspeed"

    def test_load_fsdp_yaml(self, tmp_path):
        data = _minimal_config(
            distributed={
                "strategy": "fsdp",
                "fsdp_strategy": "full_shard",
                "fsdp_offload": True,
            }
        )
        cfg_path = str(tmp_path / "config.yaml")
        with open(cfg_path, "w") as f:
            yaml.dump(data, f)
        cfg = load_config(cfg_path)
        assert cfg.distributed.strategy == "fsdp"
        assert cfg.distributed.fsdp_offload is True


# --- DeepSpeed config resolution ---


class TestDeepSpeedConfigResolution:
    def test_preset_files_exist(self):
        """Verify that all DeepSpeed preset JSON files are valid."""
        configs_dir = os.path.join(os.path.dirname(__file__), "..", "configs", "deepspeed")
        for preset in ["zero2.json", "zero3.json", "zero3_offload.json"]:
            path = os.path.join(configs_dir, preset)
            assert os.path.isfile(path), f"Missing preset: {path}"
            with open(path) as f:
                data = json.load(f)
            assert "zero_optimization" in data
            assert "stage" in data["zero_optimization"]

    def test_zero2_is_stage_2(self):
        path = os.path.join(os.path.dirname(__file__), "..", "configs", "deepspeed", "zero2.json")
        with open(path) as f:
            data = json.load(f)
        assert data["zero_optimization"]["stage"] == 2

    def test_zero3_is_stage_3(self):
        path = os.path.join(os.path.dirname(__file__), "..", "configs", "deepspeed", "zero3.json")
        with open(path) as f:
            data = json.load(f)
        assert data["zero_optimization"]["stage"] == 3

    def test_zero3_offload_has_cpu_offload(self):
        path = os.path.join(os.path.dirname(__file__), "..", "configs", "deepspeed", "zero3_offload.json")
        with open(path) as f:
            data = json.load(f)
        assert data["zero_optimization"]["stage"] == 3
        assert data["zero_optimization"]["offload_optimizer"]["device"] == "cpu"
        assert data["zero_optimization"]["offload_param"]["device"] == "cpu"

    def test_all_presets_use_auto_values(self):
        """Ensure presets use 'auto' so HF Trainer resolves values from TrainingArguments."""
        configs_dir = os.path.join(os.path.dirname(__file__), "..", "configs", "deepspeed")
        for preset in ["zero2.json", "zero3.json", "zero3_offload.json"]:
            with open(os.path.join(configs_dir, preset)) as f:
                data = json.load(f)
            assert data["train_batch_size"] == "auto"
            assert data["train_micro_batch_size_per_gpu"] == "auto"
            assert data["gradient_accumulation_steps"] == "auto"


# --- Dry-run with distributed ---


class TestDryRunDistributed:
    def test_dry_run_json_shows_distributed(self, tmp_path, capsys):
        from forgelm.cli import _run_dry_run

        cfg = ForgeConfig(**_minimal_config(distributed={"strategy": "deepspeed", "deepspeed_config": "zero3"}))
        _run_dry_run(cfg, "json")
        result = json.loads(capsys.readouterr().out)
        assert result["distributed"] == "deepspeed"

    def test_dry_run_json_no_distributed(self, capsys):
        from forgelm.cli import _run_dry_run

        cfg = ForgeConfig(**_minimal_config())
        _run_dry_run(cfg, "json")
        result = json.loads(capsys.readouterr().out)
        assert result["distributed"] is None
