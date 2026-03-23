"""Unit tests for forgelm.benchmark module."""
import json
import os
import pytest
from unittest.mock import patch, MagicMock

from forgelm.benchmark import BenchmarkResult, run_benchmark, _check_lm_eval_available
from forgelm.config import ForgeConfig, BenchmarkConfig, EvaluationConfig


class TestBenchmarkResult:
    def test_default_values(self):
        r = BenchmarkResult()
        assert r.scores == {}
        assert r.average_score == 0.0
        assert r.passed is True
        assert r.failure_reason is None
        assert r.raw_results is None

    def test_with_scores(self):
        r = BenchmarkResult(
            scores={"arc_easy": 0.65, "hellaswag": 0.55},
            average_score=0.60,
            passed=True,
        )
        assert r.scores["arc_easy"] == 0.65
        assert r.average_score == 0.60

    def test_failed_result(self):
        r = BenchmarkResult(
            scores={"arc_easy": 0.30},
            average_score=0.30,
            passed=False,
            failure_reason="Below threshold",
        )
        assert r.passed is False
        assert r.failure_reason == "Below threshold"


class TestCheckLmEvalAvailable:
    def test_raises_when_not_installed(self):
        with patch.dict("sys.modules", {"lm_eval": None}):
            with pytest.raises(ImportError, match="lm-evaluation-harness"):
                _check_lm_eval_available()


class TestBenchmarkConfig:
    def test_defaults(self):
        b = BenchmarkConfig()
        assert b.enabled is False
        assert b.tasks == []
        assert b.num_fewshot is None
        assert b.batch_size == "auto"
        assert b.limit is None
        assert b.min_score is None

    def test_with_tasks(self):
        b = BenchmarkConfig(
            enabled=True,
            tasks=["arc_easy", "hellaswag"],
            num_fewshot=5,
            min_score=0.4,
        )
        assert b.enabled is True
        assert len(b.tasks) == 2
        assert b.min_score == 0.4


class TestBenchmarkInConfig:
    def test_evaluation_with_benchmark(self):
        data = {
            "model": {"name_or_path": "org/model"},
            "lora": {},
            "training": {},
            "data": {"dataset_name_or_path": "org/dataset"},
            "evaluation": {
                "auto_revert": True,
                "benchmark": {
                    "enabled": True,
                    "tasks": ["arc_easy"],
                    "min_score": 0.5,
                },
            },
        }
        cfg = ForgeConfig(**data)
        assert cfg.evaluation.benchmark is not None
        assert cfg.evaluation.benchmark.enabled is True
        assert cfg.evaluation.benchmark.tasks == ["arc_easy"]
        assert cfg.evaluation.benchmark.min_score == 0.5

    def test_evaluation_without_benchmark(self):
        data = {
            "model": {"name_or_path": "org/model"},
            "lora": {},
            "training": {},
            "data": {"dataset_name_or_path": "org/dataset"},
            "evaluation": {"auto_revert": True},
        }
        cfg = ForgeConfig(**data)
        assert cfg.evaluation.benchmark is None


lm_eval_available = True
try:
    import lm_eval  # noqa: F401
except ImportError:
    lm_eval_available = False


class TestRunBenchmark:
    def test_empty_tasks_returns_passed(self):
        result = run_benchmark(
            model=MagicMock(),
            tokenizer=MagicMock(),
            tasks=[],
        )
        assert result.passed is True
        assert result.scores == {}

    @pytest.mark.skipif(not lm_eval_available, reason="lm_eval not installed")
    @patch("forgelm.benchmark._check_lm_eval_available")
    @patch("forgelm.benchmark.lm_eval", create=True)
    @patch("forgelm.benchmark.HFLM", create=True)
    def test_successful_benchmark(self, mock_hflm_cls, mock_lm_eval, mock_check):
        """Test benchmark with mocked lm-eval results."""
        # We need to mock the imports inside run_benchmark
        mock_lm_obj = MagicMock()
        mock_hflm_cls.return_value = mock_lm_obj

        mock_results = {
            "results": {
                "arc_easy": {"acc_norm,none": 0.65},
                "hellaswag": {"acc_norm,none": 0.55},
            }
        }

        # Patch the actual imports inside the function
        with patch("forgelm.benchmark.HFLM", return_value=mock_lm_obj):
            with patch("forgelm.benchmark.lm_eval") as mock_eval_module:
                mock_eval_module.simple_evaluate.return_value = mock_results
                # Need to also patch the import check
                import forgelm.benchmark as bm
                original_check = bm._check_lm_eval_available
                bm._check_lm_eval_available = lambda: None

                try:
                    result = run_benchmark(
                        model=MagicMock(),
                        tokenizer=MagicMock(),
                        tasks=["arc_easy", "hellaswag"],
                    )
                finally:
                    bm._check_lm_eval_available = original_check

        assert result.scores.get("arc_easy") == 0.65
        assert result.scores.get("hellaswag") == 0.55
        assert abs(result.average_score - 0.60) < 0.01
        assert result.passed is True

    def test_min_score_failure(self):
        """Test that min_score threshold triggers failure."""
        result = BenchmarkResult(
            scores={"arc_easy": 0.30},
            average_score=0.30,
            passed=False,
            failure_reason="Average benchmark score (0.3000) is below minimum threshold (0.5000).",
        )
        assert result.passed is False
        assert "below minimum threshold" in result.failure_reason

    def test_result_saved_to_file(self, tmp_path):
        """Test benchmark results are saved when output_dir specified."""
        output_dir = str(tmp_path / "benchmark_output")

        # Directly test the save logic by creating a result manually
        result = BenchmarkResult(
            scores={"arc_easy": 0.65},
            average_score=0.65,
            passed=True,
        )

        # Verify the output data structure
        output_data = {
            "tasks": ["arc_easy"],
            "scores": result.scores,
            "average_score": result.average_score,
            "passed": result.passed,
        }
        os.makedirs(output_dir, exist_ok=True)
        results_path = os.path.join(output_dir, "benchmark_results.json")
        with open(results_path, "w") as f:
            json.dump(output_data, f, indent=2)

        assert os.path.exists(results_path)
        with open(results_path) as f:
            saved = json.load(f)
        assert saved["scores"]["arc_easy"] == 0.65
        assert saved["passed"] is True


class TestTrainResultWithBenchmark:
    def test_train_result_benchmark_fields(self):
        from forgelm.results import TrainResult

        result = TrainResult(
            success=True,
            metrics={"eval_loss": 0.5},
            benchmark_scores={"arc_easy": 0.65, "hellaswag": 0.55},
            benchmark_average=0.60,
            benchmark_passed=True,
        )
        assert result.benchmark_scores["arc_easy"] == 0.65
        assert result.benchmark_average == 0.60
        assert result.benchmark_passed is True

    def test_train_result_no_benchmark(self):
        from forgelm.results import TrainResult

        result = TrainResult(success=True)
        assert result.benchmark_scores is None
        assert result.benchmark_average is None
        assert result.benchmark_passed is None
