"""Regression tests for ``forgelm.cli._no_train_modes``.

Covers P1-1 (benchmark-only loader): the loader must route through
``inference.load_model`` (not the training-time ``get_model_and_tokenizer``),
detect PEFT checkpoints by ``adapter_config.json`` presence, and pass the
adapter path through so the base model + adapter combo evaluates instead
of a fresh-init LoRA.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch


def _bench_config(minimal_config, output_dir):
    """Build a ForgeConfig with a benchmark task wired up."""
    from forgelm.config import ForgeConfig

    return ForgeConfig(
        **minimal_config(
            evaluation={
                "benchmark": {
                    "tasks": ["arc_easy"],
                    "min_score": 0.0,
                    "output_dir": str(output_dir),
                }
            }
        )
    )


def _passing_benchmark_result():
    result = MagicMock()
    result.passed = True
    result.failure_reason = None
    result.scores = {"arc_easy": 0.5}
    result.average_score = 0.5
    return result


class TestBenchmarkOnlyLoader:
    def test_plain_model_path_loads_directly(self, tmp_path, minimal_config):
        """Without adapter_config.json the path is loaded as a full model."""
        config = _bench_config(minimal_config, tmp_path / "out")
        model_dir = tmp_path / "merged_model"
        model_dir.mkdir()

        with (
            patch("forgelm.inference.load_model", return_value=(MagicMock(), MagicMock())) as load_mock,
            patch("forgelm.benchmark.run_benchmark", return_value=_passing_benchmark_result()),
        ):
            from forgelm.cli._no_train_modes import _run_benchmark_only

            _run_benchmark_only(config, str(model_dir), output_format="json")

        load_mock.assert_called_once()
        call = load_mock.call_args
        assert call.args[0] == str(model_dir)
        assert call.kwargs.get("adapter") is None

    def test_peft_checkpoint_routes_through_adapter(self, tmp_path, minimal_config):
        """When adapter_config.json is present, load_model is called with
        the base model path + adapter=<checkpoint dir>."""
        config = _bench_config(minimal_config, tmp_path / "out")
        adapter_dir = tmp_path / "adapter"
        adapter_dir.mkdir()
        (adapter_dir / "adapter_config.json").write_text(
            json.dumps({"base_model_name_or_path": "meta-llama/Llama-3-8B"})
        )

        with (
            patch("forgelm.inference.load_model", return_value=(MagicMock(), MagicMock())) as load_mock,
            patch("forgelm.benchmark.run_benchmark", return_value=_passing_benchmark_result()),
        ):
            from forgelm.cli._no_train_modes import _run_benchmark_only

            _run_benchmark_only(config, str(adapter_dir), output_format="json")

        load_mock.assert_called_once()
        call = load_mock.call_args
        assert call.args[0] == "meta-llama/Llama-3-8B", (
            f"Base model path from adapter_config.json should be the first positional arg, got {call.args[0]!r}"
        )
        assert call.kwargs.get("adapter") == str(adapter_dir), (
            "Adapter path must be forwarded so PeftModel.from_pretrained merges the saved weights"
        )

    def test_peft_checkpoint_without_base_model_fails_loudly(self, tmp_path, minimal_config):
        """If adapter_config.json lacks ``base_model_name_or_path`` we cannot
        reconstruct the base model + adapter combination; falling back to
        the adapter path would trigger a confusing ``config.json not found``
        crash deep inside PeftModel.from_pretrained.  Exit with
        EXIT_CONFIG_ERROR at the source instead.
        """
        import pytest

        from forgelm.cli._exit_codes import EXIT_CONFIG_ERROR

        config = _bench_config(minimal_config, tmp_path / "out")
        adapter_dir = tmp_path / "adapter"
        adapter_dir.mkdir()
        (adapter_dir / "adapter_config.json").write_text(json.dumps({}))

        with (
            patch("forgelm.inference.load_model", return_value=(MagicMock(), MagicMock())),
            patch("forgelm.benchmark.run_benchmark", return_value=_passing_benchmark_result()),
            pytest.raises(SystemExit) as exc_info,
        ):
            from forgelm.cli._no_train_modes import _run_benchmark_only

            _run_benchmark_only(config, str(adapter_dir), output_format="json")

        assert exc_info.value.code == EXIT_CONFIG_ERROR

    def test_peft_checkpoint_with_corrupt_adapter_config_fails_loudly(self, tmp_path, minimal_config):
        """A truncated / malformed adapter_config.json must surface an
        actionable config error rather than crashing later."""
        import pytest

        from forgelm.cli._exit_codes import EXIT_CONFIG_ERROR

        config = _bench_config(minimal_config, tmp_path / "out")
        adapter_dir = tmp_path / "adapter"
        adapter_dir.mkdir()
        (adapter_dir / "adapter_config.json").write_text("{not valid json")

        with (
            patch("forgelm.inference.load_model", return_value=(MagicMock(), MagicMock())),
            patch("forgelm.benchmark.run_benchmark", return_value=_passing_benchmark_result()),
            pytest.raises(SystemExit) as exc_info,
        ):
            from forgelm.cli._no_train_modes import _run_benchmark_only

            _run_benchmark_only(config, str(adapter_dir), output_format="json")

        assert exc_info.value.code == EXIT_CONFIG_ERROR

    def test_get_model_and_tokenizer_not_called(self, tmp_path, minimal_config):
        """Regression for P1-1: the training-time loader must not be used —
        it always wraps a fresh untrained LoRA via get_peft_model."""
        config = _bench_config(minimal_config, tmp_path / "out")
        model_dir = tmp_path / "merged_model"
        model_dir.mkdir()

        with (
            patch("forgelm.model.get_model_and_tokenizer") as bad_loader,
            patch("forgelm.inference.load_model", return_value=(MagicMock(), MagicMock())),
            patch("forgelm.benchmark.run_benchmark", return_value=_passing_benchmark_result()),
        ):
            from forgelm.cli._no_train_modes import _run_benchmark_only

            _run_benchmark_only(config, str(model_dir), output_format="json")

        bad_loader.assert_not_called()
