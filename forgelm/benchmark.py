"""Post-training benchmark evaluation via EleutherAI lm-evaluation-harness.

This module is optional — requires `pip install forgelm[eval]`.
"""
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("forgelm.benchmark")


@dataclass
class BenchmarkResult:
    """Holds the results of a benchmark evaluation run."""
    scores: Dict[str, float] = field(default_factory=dict)  # task_name -> accuracy
    average_score: float = 0.0
    passed: bool = True
    failure_reason: Optional[str] = None
    raw_results: Optional[Dict[str, Any]] = None  # full lm-eval output


def _check_lm_eval_available() -> None:
    """Check if lm-eval is installed."""
    try:
        import lm_eval  # noqa: F401
    except ImportError:
        raise ImportError(
            "lm-evaluation-harness is required for benchmarking but not installed. "
            "Install it with: pip install forgelm[eval]"
        )


def run_benchmark(
    model: Any,
    tokenizer: Any,
    tasks: List[str],
    num_fewshot: Optional[int] = None,
    batch_size: str = "auto",
    limit: Optional[int] = None,
    output_dir: Optional[str] = None,
    min_score: Optional[float] = None,
) -> BenchmarkResult:
    """Run lm-evaluation-harness benchmarks on a model.

    Args:
        model: The model to evaluate (HF model or PEFT model).
        tokenizer: The tokenizer for the model.
        tasks: List of benchmark task names (e.g. ["arc_easy", "hellaswag"]).
        num_fewshot: Number of few-shot examples. None = task default.
        batch_size: Batch size for evaluation. "auto" for automatic.
        limit: Limit number of samples per task (None = all).
        output_dir: Directory to save benchmark results JSON.
        min_score: Minimum average accuracy threshold. If below, result.passed = False.

    Returns:
        BenchmarkResult with per-task scores and pass/fail status.
    """
    if not tasks:
        logger.warning("No benchmark tasks specified. Skipping benchmark.")
        return BenchmarkResult(passed=True)

    _check_lm_eval_available()

    import lm_eval
    from lm_eval.models.huggingface import HFLM

    logger.info("Starting benchmark evaluation with tasks: %s", tasks)

    # Wrap model for lm-eval
    try:
        lm_obj = HFLM(
            pretrained=model,
            tokenizer=tokenizer,
            batch_size=batch_size,
        )
    except Exception as e:
        logger.error("Failed to initialize lm-eval model wrapper: %s", e)
        return BenchmarkResult(
            passed=False,
            failure_reason=f"Model wrapper initialization failed: {e}",
        )

    # Build task arguments
    task_kwargs = {}
    if num_fewshot is not None:
        task_kwargs["num_fewshot"] = num_fewshot

    # Run evaluation
    try:
        results = lm_eval.simple_evaluate(
            model=lm_obj,
            tasks=tasks,
            limit=limit,
            **task_kwargs,
        )
    except Exception as e:
        logger.error("Benchmark evaluation failed: %s", e)
        return BenchmarkResult(
            passed=False,
            failure_reason=f"Evaluation execution failed: {e}",
        )

    # Parse results
    scores = {}
    raw_results = results.get("results", {})

    for task_name, task_result in raw_results.items():
        # lm-eval stores metrics under various keys; prefer acc_norm, then acc
        # Use explicit None checks to avoid treating 0.0 as missing
        score = task_result.get("acc_norm,none")
        if score is None:
            score = task_result.get("acc,none")
        if score is None:
            score = task_result.get("acc_norm")
        if score is None:
            score = task_result.get("acc")
        if score is not None:
            scores[task_name] = float(score)
            logger.info("  %s: %.4f", task_name, score)
        else:
            # Try to find any metric that looks like an accuracy
            for key, value in task_result.items():
                if isinstance(value, (int, float)) and "acc" in key:
                    scores[task_name] = float(value)
                    logger.info("  %s: %.4f (%s)", task_name, value, key)
                    break
            else:
                logger.warning("  %s: no accuracy metric found in results", task_name)

    # Compute average
    average_score = sum(scores.values()) / len(scores) if scores else 0.0
    logger.info("Average benchmark score: %.4f", average_score)

    # Check minimum score threshold
    passed = True
    failure_reason = None
    if min_score is not None and average_score < min_score:
        passed = False
        failure_reason = (
            f"Average benchmark score ({average_score:.4f}) is below "
            f"minimum threshold ({min_score:.4f})."
        )
        logger.error("BENCHMARK FAILED: %s", failure_reason)

    # Save results to file
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        results_path = os.path.join(output_dir, "benchmark_results.json")
        try:
            output_data = {
                "tasks": tasks,
                "scores": scores,
                "average_score": average_score,
                "passed": passed,
                "num_fewshot": num_fewshot,
                "limit": limit,
            }
            with open(results_path, "w") as f:
                json.dump(output_data, f, indent=2)
            logger.info("Benchmark results saved to %s", results_path)
        except Exception as e:
            logger.warning("Failed to save benchmark results: %s", e)

    return BenchmarkResult(
        scores=scores,
        average_score=average_score,
        passed=passed,
        failure_reason=failure_reason,
        raw_results=raw_results,
    )
