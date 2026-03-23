"""Unit tests for forgelm.trainer module (non-GPU tests only)."""

from unittest.mock import MagicMock, patch

import pytest

from forgelm.results import TrainResult

# ForgeTrainer requires torch — skip evaluation tests if not available
torch_available = True
try:
    import torch  # noqa: F401
except ImportError:
    torch_available = False


class TestTrainResult:
    def test_success_result(self):
        result = TrainResult(
            success=True,
            metrics={"eval_loss": 0.5, "train_loss": 0.3},
            final_model_path="/path/to/model",
        )
        assert result.success is True
        assert result.metrics["eval_loss"] == 0.5
        assert result.final_model_path == "/path/to/model"
        assert result.reverted is False
        assert result.error is None

    def test_reverted_result(self):
        result = TrainResult(
            success=False,
            metrics={"eval_loss": 3.5},
            reverted=True,
        )
        assert result.success is False
        assert result.reverted is True
        assert result.final_model_path is None

    def test_error_result(self):
        result = TrainResult(
            success=False,
            error="OOM error",
        )
        assert result.success is False
        assert result.error == "OOM error"
        assert result.metrics == {}

    def test_empty_metrics_default(self):
        result = TrainResult(success=True)
        assert result.metrics == {}


@pytest.mark.skipif(not torch_available, reason="torch not installed")
class TestEvaluationChecks:
    """Test execute_evaluation_checks via a minimal ForgeTrainer mock."""

    def _make_trainer(self, auto_revert=True, max_loss=None, baseline_loss=None):
        """Create a ForgeTrainer with mocked dependencies."""
        from forgelm.config import ForgeConfig

        config_data = {
            "model": {"name_or_path": "org/model"},
            "lora": {},
            "training": {"output_dir": "/tmp/test_forge_eval"},
            "data": {"dataset_name_or_path": "org/dataset"},
            "evaluation": {
                "auto_revert": auto_revert,
                "max_acceptable_loss": max_loss,
                "baseline_loss": baseline_loss,
            },
        }
        config = ForgeConfig(**config_data)

        # Import after config to avoid heavy deps at module level
        from forgelm.trainer import ForgeTrainer

        with patch("forgelm.trainer.WebhookNotifier"):
            trainer = ForgeTrainer.__new__(ForgeTrainer)
            trainer.config = config
            trainer.dataset = {"train": ["dummy"], "validation": ["dummy"]}
            trainer.checkpoint_dir = "/tmp/test_forge_eval"
            trainer.run_name = "test_finetune"
            trainer.notifier = MagicMock()
        return trainer

    def test_no_evaluation_config(self):
        from forgelm.config import ForgeConfig
        from forgelm.trainer import ForgeTrainer

        config = ForgeConfig(
            model={"name_or_path": "org/model"},
            lora={},
            training={},
            data={"dataset_name_or_path": "org/dataset"},
        )
        with patch("forgelm.trainer.WebhookNotifier"):
            trainer = ForgeTrainer.__new__(ForgeTrainer)
            trainer.config = config
            trainer.dataset = {"train": []}
            trainer.checkpoint_dir = "/tmp/test"
            trainer.run_name = "test"
            trainer.notifier = MagicMock()

        assert trainer.execute_evaluation_checks("/tmp/test/final", {"eval_loss": 5.0}) is True

    def test_max_loss_exceeded(self):
        trainer = self._make_trainer(max_loss=2.0)
        result = trainer.execute_evaluation_checks("/tmp/nonexistent", {"eval_loss": 3.0})
        assert result is False

    def test_max_loss_within_bounds(self):
        trainer = self._make_trainer(max_loss=2.0)
        result = trainer.execute_evaluation_checks("/tmp/nonexistent", {"eval_loss": 1.5})
        assert result is True

    def test_baseline_regression(self):
        trainer = self._make_trainer(baseline_loss=1.0)
        result = trainer.execute_evaluation_checks("/tmp/nonexistent", {"eval_loss": 1.5})
        assert result is False

    def test_baseline_improvement(self):
        trainer = self._make_trainer(baseline_loss=2.0)
        result = trainer.execute_evaluation_checks("/tmp/nonexistent", {"eval_loss": 1.5})
        assert result is True

    def test_nan_eval_loss(self):
        trainer = self._make_trainer(max_loss=2.0)
        result = trainer.execute_evaluation_checks("/tmp/nonexistent", {"eval_loss": float("nan")})
        assert result is False

    def test_inf_eval_loss(self):
        trainer = self._make_trainer(max_loss=2.0)
        result = trainer.execute_evaluation_checks("/tmp/nonexistent", {"eval_loss": float("inf")})
        assert result is False

    def test_missing_eval_loss(self):
        trainer = self._make_trainer(max_loss=2.0)
        result = trainer.execute_evaluation_checks("/tmp/nonexistent", {"train_loss": 0.5})
        assert result is True  # Skip check when no eval_loss

    def test_no_validation_data(self):
        trainer = self._make_trainer(max_loss=2.0)
        trainer.dataset = {"train": []}  # No validation
        result = trainer.execute_evaluation_checks("/tmp/nonexistent", {"eval_loss": 5.0})
        assert result is True  # Skip when no validation

    def test_auto_revert_disabled(self):
        trainer = self._make_trainer(auto_revert=False, max_loss=0.1)
        result = trainer.execute_evaluation_checks("/tmp/nonexistent", {"eval_loss": 5.0})
        assert result is True  # auto_revert=False means always pass
