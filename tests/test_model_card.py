"""Unit tests for model card generation."""

import os

from forgelm.config import ForgeConfig


def _minimal_config(**overrides):
    data = {
        "model": {"name_or_path": "org/test-model"},
        "lora": {"r": 16, "alpha": 32, "use_dora": True},
        "training": {"num_train_epochs": 3},
        "data": {"dataset_name_or_path": "org/dataset"},
    }
    data.update(overrides)
    return data


class TestGenerateModelCard:
    def test_generates_readme(self, tmp_path):
        from forgelm.model_card import generate_model_card

        config = ForgeConfig(**_minimal_config())
        final_path = str(tmp_path / "model")
        card_path = generate_model_card(
            config=config,
            metrics={"eval_loss": 1.25, "train_loss": 0.8},
            final_path=final_path,
        )
        assert os.path.isfile(card_path)
        assert card_path.endswith("README.md")

        content = open(card_path).read()
        assert "org/test-model" in content
        assert "eval_loss" in content
        assert "ForgeLM" in content

    def test_includes_benchmark_section(self, tmp_path):
        from forgelm.model_card import generate_model_card

        config = ForgeConfig(**_minimal_config())
        final_path = str(tmp_path / "model")
        card_path = generate_model_card(
            config=config,
            metrics={"eval_loss": 0.5},
            final_path=final_path,
            benchmark_scores={"arc_easy": 0.72, "hellaswag": 0.55},
            benchmark_average=0.635,
        )
        content = open(card_path).read()
        assert "Benchmark" in content
        assert "arc_easy" in content
        assert "0.72" in content

    def test_no_benchmark_section_when_none(self, tmp_path):
        from forgelm.model_card import generate_model_card

        config = ForgeConfig(**_minimal_config())
        final_path = str(tmp_path / "model")
        card_path = generate_model_card(
            config=config,
            metrics={"eval_loss": 0.5},
            final_path=final_path,
        )
        content = open(card_path).read()
        assert "Benchmark Results" not in content

    def test_excludes_auth_from_config(self, tmp_path):
        from forgelm.model_card import generate_model_card

        config = ForgeConfig(**_minimal_config(auth={"hf_token": "hf_SECRET"}))
        final_path = str(tmp_path / "model")
        card_path = generate_model_card(
            config=config,
            metrics={},
            final_path=final_path,
        )
        content = open(card_path).read()
        assert "hf_SECRET" not in content

    def test_dora_tag_in_frontmatter(self, tmp_path):
        from forgelm.model_card import generate_model_card

        config = ForgeConfig(**_minimal_config())
        final_path = str(tmp_path / "model")
        card_path = generate_model_card(
            config=config,
            metrics={},
            final_path=final_path,
        )
        content = open(card_path).read()
        assert "dora" in content.lower()

    def test_empty_metrics(self, tmp_path):
        from forgelm.model_card import generate_model_card

        config = ForgeConfig(**_minimal_config())
        final_path = str(tmp_path / "model")
        card_path = generate_model_card(
            config=config,
            metrics={},
            final_path=final_path,
        )
        assert os.path.isfile(card_path)

    def test_webhook_url_excluded_from_model_card(self, tmp_path):
        """Webhook URLs must not appear in the generated model card YAML config block."""
        from forgelm.model_card import generate_model_card

        secret_url = "https://hooks.slack.com/services/SECRET_TOKEN/MORE_SECRET"
        config = ForgeConfig(**_minimal_config(webhook={"url": secret_url}))
        final_path = str(tmp_path / "model")
        card_path = generate_model_card(
            config=config,
            metrics={"eval_loss": 0.5},
            final_path=final_path,
        )
        content = open(card_path).read()
        assert secret_url not in content, "Webhook URL must not appear in model card"
        assert "SECRET_TOKEN" not in content
