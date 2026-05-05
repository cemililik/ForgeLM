"""Unit tests for data.py edge cases (multimodal, mix_ratio zero weight)."""

import pytest
import yaml

from forgelm.config import ForgeConfig


class TestMultimodalConfig:
    def test_multimodal_enabled_in_config(self, minimal_config):
        cfg = ForgeConfig(
            **minimal_config(
                model={
                    "name_or_path": "org/vlm-model",
                    "multimodal": {"enabled": True, "image_column": "img", "text_column": "caption"},
                }
            )
        )
        assert cfg.model.multimodal.enabled is True
        assert cfg.model.multimodal.image_column == "img"

    def test_multimodal_disabled_by_default(self, minimal_config):
        cfg = ForgeConfig(**minimal_config())
        assert cfg.model.multimodal is None

    def test_multimodal_config_from_yaml(self, tmp_path, minimal_config):
        from forgelm.config import load_config

        data = minimal_config(
            model={
                "name_or_path": "org/vlm",
                "multimodal": {"enabled": True},
            }
        )
        cfg_path = str(tmp_path / "config.yaml")
        with open(cfg_path, "w") as f:
            yaml.dump(data, f)
        cfg = load_config(cfg_path)
        assert cfg.model.multimodal.enabled is True


class TestMixRatioEdgeCases:
    def test_zero_weight_config_raises(self, minimal_config):
        """mix_ratio with all zeros must be rejected — meaningless sampling weights."""
        with pytest.raises(Exception, match="mix_ratio values cannot all be zero"):
            ForgeConfig(
                **minimal_config(
                    data={
                        "dataset_name_or_path": "org/dataset",
                        "extra_datasets": ["org/extra"],
                        "mix_ratio": [0.0, 0.0],
                    }
                )
            )

    def test_single_dataset_no_extra(self, minimal_config):
        cfg = ForgeConfig(**minimal_config(data={"dataset_name_or_path": "org/dataset"}))
        assert cfg.data.extra_datasets is None
        assert cfg.data.mix_ratio is None


class TestGrpoRewardModelConfig:
    def test_default_none(self, minimal_config):
        cfg = ForgeConfig(**minimal_config(training={"trainer_type": "grpo"}))
        assert cfg.training.grpo_reward_model is None

    def test_custom_reward_model(self, minimal_config):
        cfg = ForgeConfig(
            **minimal_config(
                training={
                    "trainer_type": "grpo",
                    "grpo_reward_model": "org/reward-model",
                }
            )
        )
        assert cfg.training.grpo_reward_model == "org/reward-model"

    def test_grpo_config_from_yaml(self, tmp_path, minimal_config):
        from forgelm.config import load_config

        data = minimal_config(
            training={
                "trainer_type": "grpo",
                "grpo_reward_model": "org/reward",
                "grpo_num_generations": 8,
            }
        )
        cfg_path = str(tmp_path / "config.yaml")
        with open(cfg_path, "w") as f:
            yaml.dump(data, f)
        cfg = load_config(cfg_path)
        assert cfg.training.grpo_reward_model == "org/reward"
        assert cfg.training.grpo_num_generations == 8


class TestWebhookTimeoutConfig:
    def test_default_timeout(self):
        from forgelm.config import WebhookConfig

        # Default raised from 5s → 10s in v0.5.5 (Faz 28 / F-compliance-106).
        # Slack/Teams gateway latency spikes regularly cross 5s in
        # production, and a webhook timeout silently degrades the audit
        # chain (webhook delivery is best-effort).  10s leaves head-room
        # without blocking training-pipeline forward progress.
        w = WebhookConfig()
        assert w.timeout == 10

    def test_custom_timeout(self):
        from forgelm.config import WebhookConfig

        w = WebhookConfig(timeout=15)
        assert w.timeout == 15

    def test_timeout_in_full_config(self, minimal_config):
        cfg = ForgeConfig(**minimal_config(webhook={"url": "https://example.com", "timeout": 10}))
        assert cfg.webhook.timeout == 10
