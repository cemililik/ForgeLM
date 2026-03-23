"""Unit tests for forgelm.config module."""
import os

import pytest
import yaml

from forgelm.config import (
    EvaluationConfig,
    ForgeConfig,
    LoraConfigModel,
    ModelConfig,
    TrainingConfig,
    WebhookConfig,
    load_config,
)

# --- Helper ---

def _write_yaml(data: dict, path: str) -> str:
    with open(path, "w") as f:
        yaml.dump(data, f)
    return path


def _minimal_config() -> dict:
    """Smallest valid config dict."""
    return {
        "model": {"name_or_path": "some-org/some-model"},
        "lora": {},
        "training": {},
        "data": {"dataset_name_or_path": "some-org/some-dataset"},
    }


# --- ModelConfig ---

class TestModelConfig:
    def test_defaults(self):
        m = ModelConfig(name_or_path="org/model")
        assert m.backend == "transformers"
        assert m.load_in_4bit is True
        assert m.trust_remote_code is False
        assert m.max_length == 2048
        assert m.bnb_4bit_quant_type == "nf4"
        assert m.bnb_4bit_compute_dtype == "auto"

    def test_trust_remote_code_explicit(self):
        m = ModelConfig(name_or_path="org/model", trust_remote_code=True)
        assert m.trust_remote_code is True

    def test_unsloth_backend(self):
        m = ModelConfig(name_or_path="org/model", backend="unsloth")
        assert m.backend == "unsloth"


# --- LoraConfigModel ---

class TestLoraConfig:
    def test_defaults(self):
        lora = LoraConfigModel()
        assert lora.r == 8
        assert lora.alpha == 16
        assert lora.dropout == 0.1
        assert lora.bias == "none"
        assert lora.use_dora is False
        assert lora.target_modules == ["q_proj", "v_proj"]
        assert lora.task_type == "CAUSAL_LM"

    def test_custom_target_modules(self):
        lora = LoraConfigModel(target_modules=["q_proj", "k_proj", "v_proj", "o_proj"])
        assert len(lora.target_modules) == 4

    def test_dora_enabled(self):
        lora = LoraConfigModel(use_dora=True)
        assert lora.use_dora is True


# --- TrainingConfig ---

class TestTrainingConfig:
    def test_defaults(self):
        t = TrainingConfig()
        assert t.output_dir == "./checkpoints"
        assert t.final_model_dir == "final_model"
        assert t.merge_adapters is False
        assert t.packing is False

    def test_custom_values(self):
        t = TrainingConfig(learning_rate=1e-4, num_train_epochs=5)
        assert t.learning_rate == 1e-4
        assert t.num_train_epochs == 5


# --- EvaluationConfig ---

class TestEvaluationConfig:
    def test_defaults(self):
        e = EvaluationConfig()
        assert e.auto_revert is False
        assert e.max_acceptable_loss is None
        assert e.baseline_loss is None

    def test_auto_revert_with_max_loss(self):
        e = EvaluationConfig(auto_revert=True, max_acceptable_loss=2.5)
        assert e.auto_revert is True
        assert e.max_acceptable_loss == 2.5


# --- WebhookConfig ---

class TestWebhookConfig:
    def test_defaults(self):
        w = WebhookConfig()
        assert w.url is None
        assert w.url_env is None
        assert w.notify_on_start is True
        assert w.notify_on_success is True
        assert w.notify_on_failure is True

    def test_url_env(self):
        w = WebhookConfig(url_env="MY_WEBHOOK_URL")
        assert w.url_env == "MY_WEBHOOK_URL"


# --- ForgeConfig (full config) ---

class TestForgeConfig:
    def test_minimal_config(self):
        cfg = ForgeConfig(**_minimal_config())
        assert cfg.model.name_or_path == "some-org/some-model"
        assert cfg.auth is None
        assert cfg.evaluation is None
        assert cfg.webhook is None

    def test_full_config(self):
        data = _minimal_config()
        data["auth"] = {"hf_token": "hf_test"}
        data["evaluation"] = {"auto_revert": True, "max_acceptable_loss": 2.0}
        data["webhook"] = {"url": "https://example.com/hook"}
        cfg = ForgeConfig(**data)
        assert cfg.auth.hf_token == "hf_test"
        assert cfg.evaluation.auto_revert is True
        assert cfg.webhook.url == "https://example.com/hook"

    def test_invalid_type_raises(self):
        data = _minimal_config()
        data["model"]["max_length"] = "not_a_number"
        with pytest.raises((ValueError, TypeError)):
            ForgeConfig(**data)

    def test_missing_required_field(self):
        data = _minimal_config()
        del data["data"]["dataset_name_or_path"]
        with pytest.raises((ValueError, TypeError, KeyError)):
            ForgeConfig(**data)


# --- load_config ---

class TestLoadConfig:
    def test_valid_file(self, tmp_path):
        cfg_path = str(tmp_path / "config.yaml")
        _write_yaml(_minimal_config(), cfg_path)
        cfg = load_config(cfg_path)
        assert isinstance(cfg, ForgeConfig)
        assert cfg.model.name_or_path == "some-org/some-model"

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/config.yaml")

    def test_invalid_yaml_raises(self, tmp_path):
        from forgelm.config import ConfigError
        cfg_path = str(tmp_path / "bad.yaml")
        with open(cfg_path, "w") as f:
            f.write(": : invalid yaml [[[")
        with pytest.raises(ConfigError):
            load_config(cfg_path)

    def test_config_template_parses(self):
        """Ensure the shipped config_template.yaml is always valid."""
        template_path = os.path.join(
            os.path.dirname(__file__), "..", "config_template.yaml"
        )
        if os.path.exists(template_path):
            cfg = load_config(template_path)
            assert cfg.model.name_or_path

    def test_trust_remote_code_in_yaml(self, tmp_path):
        data = _minimal_config()
        data["model"]["trust_remote_code"] = True
        cfg_path = str(tmp_path / "config.yaml")
        _write_yaml(data, cfg_path)
        cfg = load_config(cfg_path)
        assert cfg.model.trust_remote_code is True

    def test_extra_fields_ignored_or_error(self, tmp_path):
        """Extra unknown keys should not cause silent corruption."""
        data = _minimal_config()
        data["model"]["unknown_field_xyz"] = 42
        cfg_path = str(tmp_path / "config.yaml")
        _write_yaml(data, cfg_path)
        # Pydantic v2 ignores extra fields by default — config should still load
        cfg = load_config(cfg_path)
        assert cfg.model.name_or_path == "some-org/some-model"
