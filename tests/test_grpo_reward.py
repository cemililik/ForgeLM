"""Regression tests for GRPO reward model callable wrapping.

Verifies that when grpo_reward_model is set, _build_trainer constructs a
Python callable (not a plain string) and that the callable has the expected
interface: accepts a list of strings, returns a list of floats.
"""

from unittest.mock import MagicMock, patch

import pytest

# ForgeTrainer requires torch — skip all tests if not available
torch_available = True
try:
    import torch  # noqa: F401
except ImportError:
    torch_available = False


def _make_grpo_config(reward_model_path, output_dir=None):
    """Build a minimal ForgeConfig with grpo trainer and a reward model path."""
    from forgelm.config import ForgeConfig

    data = {
        "model": {"name_or_path": "org/model"},
        "lora": {},
        "training": {
            "trainer_type": "grpo",
            "grpo_reward_model": reward_model_path,
            "output_dir": output_dir or "./checkpoints",
        },
        "data": {"dataset_name_or_path": "org/dataset"},
    }
    return ForgeConfig(**data)


@pytest.mark.skipif(not torch_available, reason="torch not installed")
class TestGrpoRewardCallable:
    def test_reward_funcs_is_callable_list(self, tmp_path):
        """When grpo_reward_model is configured, reward_funcs must be a list of callables."""
        from forgelm.trainer import ForgeTrainer

        config = _make_grpo_config("org/reward-model", output_dir=str(tmp_path))

        model = MagicMock()
        tokenizer = MagicMock()
        dataset = {"train": list(range(10))}

        # Build trainer skeleton without heavy init
        trainer = ForgeTrainer.__new__(ForgeTrainer)
        trainer.model = model
        trainer.tokenizer = tokenizer
        trainer.config = config
        trainer.dataset = dataset
        trainer.checkpoint_dir = str(tmp_path)
        trainer.run_name = "grpo_test"
        trainer.notifier = MagicMock()
        trainer.audit = MagicMock()

        # Mock out the heavy GRPO Trainer construction
        mock_grpo_trainer = MagicMock()
        captured_kwargs = {}

        def fake_grpo_trainer(**kwargs):
            captured_kwargs.update(kwargs)
            return mock_grpo_trainer

        mock_rw_model = MagicMock()
        mock_rw_model.device = "cpu"
        # Return logits shaped (N, 1)
        import torch

        mock_rw_model.return_value.logits = torch.tensor([[0.9], [0.2], [0.7]])

        mock_rw_tokenizer = MagicMock()
        mock_rw_tokenizer.return_value = {
            "input_ids": torch.zeros((3, 10), dtype=torch.long),
            "attention_mask": torch.ones((3, 10), dtype=torch.long),
        }

        with (
            patch("forgelm.trainer.SFTTrainer"),
            patch("forgelm.trainer.SFTConfig"),
            patch("trl.GRPOTrainer", side_effect=fake_grpo_trainer),
            patch("trl.GRPOConfig", return_value=MagicMock()),
            patch(
                "transformers.AutoModelForSequenceClassification.from_pretrained",
                return_value=mock_rw_model,
            ),
            patch(
                "transformers.AutoTokenizer.from_pretrained",
                return_value=mock_rw_tokenizer,
            ),
        ):
            trainer._build_trainer(callbacks=[])

        reward_funcs = captured_kwargs.get("reward_funcs")
        assert reward_funcs is not None, "reward_funcs was not passed to GRPOTrainer"
        assert isinstance(reward_funcs, list), "reward_funcs should be a list"
        assert len(reward_funcs) == 1, "reward_funcs should have exactly one element"
        assert callable(reward_funcs[0]), "reward_funcs[0] must be callable"

    def test_reward_callable_returns_float_list(self, tmp_path):
        """The reward callable must accept a list of strings and return a list of floats."""
        import torch

        from forgelm.trainer import ForgeTrainer

        config = _make_grpo_config("org/reward-model", output_dir=str(tmp_path))

        trainer = ForgeTrainer.__new__(ForgeTrainer)
        trainer.model = MagicMock()
        trainer.tokenizer = MagicMock()
        trainer.config = config
        trainer.dataset = {"train": list(range(10))}
        trainer.checkpoint_dir = str(tmp_path)
        trainer.run_name = "grpo_test"
        trainer.notifier = MagicMock()
        trainer.audit = MagicMock()

        mock_rw_model = MagicMock()
        mock_rw_model.device = "cpu"
        # Simulate reward model returning logits for 2 completions
        fake_logits = torch.tensor([[1.5], [-0.3]])
        mock_rw_model.return_value.logits = fake_logits

        mock_rw_tokenizer = MagicMock()
        # Tokenizer returns a dict-like object with .items()
        fake_encoded = {
            "input_ids": torch.zeros((2, 10), dtype=torch.long),
            "attention_mask": torch.ones((2, 10), dtype=torch.long),
        }
        mock_rw_tokenizer.return_value = fake_encoded

        captured_kwargs = {}

        def fake_grpo_trainer(**kwargs):
            captured_kwargs.update(kwargs)
            return MagicMock()

        with (
            patch("trl.GRPOTrainer", side_effect=fake_grpo_trainer),
            patch("trl.GRPOConfig", return_value=MagicMock()),
            patch(
                "transformers.AutoModelForSequenceClassification.from_pretrained",
                return_value=mock_rw_model,
            ),
            patch(
                "transformers.AutoTokenizer.from_pretrained",
                return_value=mock_rw_tokenizer,
            ),
        ):
            trainer._build_trainer(callbacks=[])

        reward_fn = captured_kwargs["reward_funcs"][0]

        completions = ["Hello world", "This is a test"]
        result = reward_fn(completions)

        assert isinstance(result, list), "reward callable must return a list"
        assert len(result) == 2, "result length must match number of completions"
        assert all(isinstance(v, float) for v in result), "all reward values must be floats"

    def test_no_reward_model_no_reward_funcs(self, tmp_path):
        """When grpo_reward_model is not set, reward_funcs must not be passed."""
        from forgelm.config import ForgeConfig
        from forgelm.trainer import ForgeTrainer

        config_data = {
            "model": {"name_or_path": "org/model"},
            "lora": {},
            "training": {
                "trainer_type": "grpo",
                "output_dir": str(tmp_path),
            },
            "data": {"dataset_name_or_path": "org/dataset"},
        }
        config = ForgeConfig(**config_data)

        trainer = ForgeTrainer.__new__(ForgeTrainer)
        trainer.model = MagicMock()
        trainer.tokenizer = MagicMock()
        trainer.config = config
        trainer.dataset = {"train": list(range(10))}
        trainer.checkpoint_dir = str(tmp_path)
        trainer.run_name = "grpo_no_reward"
        trainer.notifier = MagicMock()
        trainer.audit = MagicMock()

        captured_kwargs = {}

        def fake_grpo_trainer(**kwargs):
            captured_kwargs.update(kwargs)
            return MagicMock()

        with (
            patch("trl.GRPOTrainer", side_effect=fake_grpo_trainer),
            patch("trl.GRPOConfig", return_value=MagicMock()),
        ):
            trainer._build_trainer(callbacks=[])

        # reward_funcs key should either not be present or be an empty list
        reward_funcs = captured_kwargs.get("reward_funcs", [])
        assert reward_funcs == [] or reward_funcs is None, (
            "reward_funcs should not be populated when grpo_reward_model is not set"
        )
