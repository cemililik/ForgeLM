"""Tests for GPU cost estimation feature."""

import pytest

from forgelm.config import ForgeConfig, TrainingConfig
from forgelm.results import TrainResult
from tests.conftest import minimal_config


class TestCostConfig:
    def test_default_none(self):
        tc = TrainingConfig()
        assert tc.gpu_cost_per_hour is None

    def test_custom_cost(self):
        tc = TrainingConfig(gpu_cost_per_hour=3.50)
        assert tc.gpu_cost_per_hour == pytest.approx(3.50)

    def test_in_full_config(self):
        cfg = ForgeConfig(**minimal_config(training={"gpu_cost_per_hour": 2.00}))
        assert cfg.training.gpu_cost_per_hour == pytest.approx(2.00)

    def test_config_template_still_parses(self):
        from forgelm.config import load_config

        cfg = load_config("config_template.yaml")
        assert cfg.training.gpu_cost_per_hour is None


class TestTrainResultCost:
    def test_default_none(self):
        r = TrainResult(success=True)
        assert r.estimated_cost_usd is None

    def test_with_cost(self):
        r = TrainResult(success=True, estimated_cost_usd=0.1234)
        assert r.estimated_cost_usd == pytest.approx(0.1234)


class TestGpuPricing:
    """Test the GPU pricing lookup logic without requiring GPU hardware."""

    def test_known_gpus_have_prices(self):
        """Import the pricing dict and verify key GPUs are present."""
        # Import the class to access pricing
        pytest.importorskip("torch")
        from forgelm.trainer import ForgeTrainer

        pricing = ForgeTrainer._GPU_PRICING
        assert "Tesla T4" in pricing
        assert "NVIDIA A100-SXM4-80GB" in pricing
        assert "NVIDIA H100 80GB HBM3" in pricing

    def test_prices_are_positive(self):
        pytest.importorskip("torch")
        from forgelm.trainer import ForgeTrainer

        for gpu, price in ForgeTrainer._GPU_PRICING.items():
            assert price > 0, f"{gpu} has non-positive price: {price}"

    def test_price_ordering_reasonable(self):
        """Sanity check: H100 should cost more than T4."""
        pytest.importorskip("torch")
        from forgelm.trainer import ForgeTrainer

        pricing = ForgeTrainer._GPU_PRICING
        assert pricing["NVIDIA H100 80GB HBM3"] > pricing["Tesla T4"]
        assert pricing["NVIDIA A100-SXM4-80GB"] > pricing["Tesla T4"]


class TestCostInJsonOutput:
    def test_json_output_includes_cost(self):
        """Verify _output_result includes cost when present."""
        import io
        import json
        import sys

        from forgelm.cli import _output_result

        r = TrainResult(
            success=True,
            estimated_cost_usd=0.5678,
            resource_usage={"gpu_hours": 0.162, "estimated_cost_usd": 0.5678},
        )

        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            _output_result(r, "json")
        finally:
            sys.stdout = old_stdout

        output = json.loads(captured.getvalue())
        assert output["estimated_cost_usd"] == pytest.approx(0.5678)
        assert output["resource_usage"]["gpu_hours"] == pytest.approx(0.162)

    def test_json_output_omits_cost_when_none(self):
        import io
        import json
        import sys

        from forgelm.cli import _output_result

        r = TrainResult(success=True)

        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            _output_result(r, "json")
        finally:
            sys.stdout = old_stdout

        output = json.loads(captured.getvalue())
        assert "estimated_cost_usd" not in output
