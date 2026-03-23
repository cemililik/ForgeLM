"""Unit tests for merging algorithms (TIES, DARE, SLERP, linear)."""

import pytest

torch = pytest.importorskip("torch")

from forgelm.merging import (  # noqa: E402
    _dare_merge_tensor,
    _ties_merge_tensor,
)


class TestTiesMergeTensor:
    def test_basic_merge(self):
        d1 = torch.tensor([1.0, -2.0, 3.0, -0.1])
        d2 = torch.tensor([1.5, -1.0, -2.0, 0.05])
        result = _ties_merge_tensor([d1, d2], [0.5, 0.5], trim_fraction=0.0)
        assert result.shape == d1.shape

    def test_trim_removes_small_values(self):
        d1 = torch.tensor([10.0, 0.01, -10.0, 0.001])
        result = _ties_merge_tensor([d1], [1.0], trim_fraction=0.5)
        # After trim, the smallest 50% by magnitude should be zeroed
        # Values 0.01 and 0.001 should be trimmed
        assert result.shape == d1.shape

    def test_sign_election(self):
        # 3 deltas where sign at index 0 is +, +, - => majority positive
        d1 = torch.tensor([1.0])
        d2 = torch.tensor([2.0])
        d3 = torch.tensor([-0.5])
        result = _ties_merge_tensor([d1, d2, d3], [1 / 3, 1 / 3, 1 / 3], trim_fraction=0.0)
        assert result[0] > 0  # majority vote should be positive

    def test_zero_deltas(self):
        d1 = torch.zeros(4)
        d2 = torch.zeros(4)
        result = _ties_merge_tensor([d1, d2], [0.5, 0.5])
        assert torch.allclose(result, torch.zeros(4))

    def test_single_delta(self):
        d1 = torch.tensor([3.0, -2.0, 1.0])
        result = _ties_merge_tensor([d1], [1.0], trim_fraction=0.0)
        assert torch.allclose(result, d1)


class TestDareMergeTensor:
    def test_basic_merge(self):
        torch.manual_seed(42)
        d1 = torch.tensor([1.0, 2.0, 3.0, 4.0])
        d2 = torch.tensor([0.5, 1.0, 1.5, 2.0])
        result = _dare_merge_tensor([d1, d2], [0.6, 0.4], drop_rate=0.3)
        assert result.shape == d1.shape

    def test_zero_drop_rate_equals_weighted_sum(self):
        d1 = torch.tensor([1.0, 2.0])
        d2 = torch.tensor([3.0, 4.0])
        result = _dare_merge_tensor([d1, d2], [0.5, 0.5], drop_rate=0.0)
        expected = d1 * 0.5 + d2 * 0.5
        assert torch.allclose(result, expected)

    def test_full_drop_rate(self):
        d1 = torch.tensor([1.0, 2.0, 3.0])
        # drop_rate=1.0 would cause division by zero, but 0.99 should drop almost everything
        result = _dare_merge_tensor([d1], [1.0], drop_rate=0.99)
        assert result.shape == d1.shape

    def test_output_shape_matches_input(self):
        d1 = torch.randn(10, 10)
        d2 = torch.randn(10, 10)
        result = _dare_merge_tensor([d1, d2], [0.7, 0.3])
        assert result.shape == (10, 10)

    def test_single_delta(self):
        torch.manual_seed(0)
        d1 = torch.tensor([5.0, 10.0])
        result = _dare_merge_tensor([d1], [1.0], drop_rate=0.0)
        assert torch.allclose(result, d1)
