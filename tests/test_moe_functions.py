"""Unit tests for MoE expert quantization and freezing functions."""

from unittest.mock import MagicMock

import pytest

torch = pytest.importorskip("torch")

from forgelm.model import _apply_moe_expert_quantization, _freeze_unselected_experts


def _make_mock_model(num_experts=4):
    """Create a mock model with expert-like named parameters."""
    model = MagicMock()
    params = {}
    modules = {}

    for layer in range(2):
        for expert_idx in range(num_experts):
            name = f"model.layers.{layer}.mlp.experts.{expert_idx}.weight"
            param = torch.randn(16, 16, requires_grad=True)
            params[name] = param

            mod = MagicMock()
            mod.weight = MagicMock()
            mod.weight.data = param.data.clone()
            mod.weight.requires_grad = True
            modules[name.rsplit(".", 1)[0]] = mod

    model.named_parameters.return_value = list(params.items())
    model.named_modules.return_value = list(modules.items())
    return model, params


class TestApplyMoeExpertQuantization:
    def test_runs_without_error(self):
        model, _ = _make_mock_model(4)
        # Should not raise
        _apply_moe_expert_quantization(model)

    def test_logs_info(self, caplog):
        import logging

        model, _ = _make_mock_model(4)
        with caplog.at_level(logging.INFO, logger="forgelm.model"):
            _apply_moe_expert_quantization(model)
        # Should log something about quantization
        assert "quantization" in caplog.text.lower() or "expert" in caplog.text.lower()


class TestFreezeUnselectedExperts:
    def test_freezes_unselected(self):
        model, params = _make_mock_model(4)
        _freeze_unselected_experts(model, "0,1", 4)

        # Experts 2 and 3 should be frozen (requires_grad=False)
        frozen_count = sum(1 for _, p in params.items() if not p.requires_grad)
        # Experts 0,1 remain trainable; experts 2,3 frozen
        assert frozen_count > 0

    def test_all_experts_no_freeze(self):
        model, params = _make_mock_model(4)
        _freeze_unselected_experts(model, "0,1,2,3", 4)

        # All selected — nothing should be frozen
        frozen_count = sum(1 for _, p in params.items() if not p.requires_grad)
        assert frozen_count == 0

    def test_invalid_format_warns(self, caplog):
        import logging

        model, _ = _make_mock_model(4)
        with caplog.at_level(logging.WARNING, logger="forgelm.model"):
            _freeze_unselected_experts(model, "abc,def", 4)
        assert "Invalid experts_to_train" in caplog.text

    def test_out_of_range_indices_warns(self, caplog):
        import logging

        model, _ = _make_mock_model(4)
        with caplog.at_level(logging.WARNING, logger="forgelm.model"):
            _freeze_unselected_experts(model, "0,1,99", 4)
        assert "exceed" in caplog.text.lower() or "99" in caplog.text

    def test_single_expert(self):
        model, params = _make_mock_model(4)
        _freeze_unselected_experts(model, "2", 4)

        # Only expert 2 trainable — experts 0,1,3 frozen
        frozen_count = sum(1 for _, p in params.items() if not p.requires_grad)
        assert frozen_count > 0
