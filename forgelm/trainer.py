import logging
import math
import torch
import os
import shutil
from trl import SFTTrainer, SFTConfig
from transformers import TrainingArguments, DefaultDataCollator, EarlyStoppingCallback
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from .webhook import WebhookNotifier

logger = logging.getLogger("forgelm.trainer")


@dataclass
class TrainResult:
    """Result of a ForgeLM training run."""
    success: bool
    metrics: Dict[str, float] = field(default_factory=dict)
    final_model_path: Optional[str] = None
    reverted: bool = False
    error: Optional[str] = None
    benchmark_scores: Optional[Dict[str, float]] = None
    benchmark_average: Optional[float] = None
    benchmark_passed: Optional[bool] = None


class ForgeTrainer:
    """Orchestrates the training process for ForgeLM using TRL SFTTrainer."""
    def __init__(self, model: Any, tokenizer: Any, config: Any, dataset: Dict[str, Any]):
        self.model = model
        self.tokenizer = tokenizer
        self.config = config
        self.dataset = dataset
        self.checkpoint_dir = self.config.training.output_dir
        self.notifier = WebhookNotifier(config)
        self.run_name = config.model.name_or_path.split("/")[-1] + "_finetune"

        os.makedirs(self.checkpoint_dir, exist_ok=True)

        # Validate evaluation config early
        self._validate_evaluation_config()

    def _validate_evaluation_config(self) -> None:
        """Warn about evaluation configuration issues before training starts."""
        eval_cfg = self.config.evaluation
        if not eval_cfg or not eval_cfg.auto_revert:
            return

        if not self.dataset.get("validation"):
            logger.warning(
                "auto_revert is enabled but no validation split exists. "
                "Evaluation checks will be skipped. Provide a validation set "
                "or set auto_revert=false."
            )

        if eval_cfg.max_acceptable_loss is None and eval_cfg.baseline_loss is None:
            logger.warning(
                "auto_revert is enabled but neither max_acceptable_loss nor "
                "baseline_loss is configured. Baseline will be computed automatically "
                "if a validation set is available."
            )

    def _get_training_args(self) -> SFTConfig:
        return SFTConfig(
            output_dir=self.checkpoint_dir,
            num_train_epochs=self.config.training.num_train_epochs,
            per_device_train_batch_size=self.config.training.per_device_train_batch_size,
            gradient_accumulation_steps=self.config.training.gradient_accumulation_steps,
            learning_rate=self.config.training.learning_rate,
            warmup_ratio=self.config.training.warmup_ratio,
            weight_decay=self.config.training.weight_decay,
            eval_steps=self.config.training.eval_steps,
            save_steps=self.config.training.save_steps,
            logging_steps=50,
            eval_strategy="steps",
            save_strategy="steps",
            save_total_limit=self.config.training.save_total_limit,
            load_best_model_at_end=True,
            metric_for_best_model="eval_loss",
            greater_is_better=False,
            gradient_checkpointing=True,
            optim="adamw_torch_fused" if torch.cuda.is_available() else "adamw_torch",
            fp16=False,
            bf16=False,
            no_cuda=not torch.cuda.is_available(),
            report_to="tensorboard",
            max_length=self.config.model.max_length,
            packing=bool(getattr(self.config.training, "packing", False)),
            dataset_text_field="text" # SFTConfig needs this
        )

    def execute_evaluation_checks(self, final_path: str, metrics: Dict[str, float]) -> bool:
        """Evaluates final loss against constraints. Returns True if acceptable, False if reverted."""
        if not self.config.evaluation or not self.config.evaluation.auto_revert:
            return True

        # No validation data means we can't evaluate
        if not self.dataset.get("validation"):
            logger.warning("Skipping evaluation checks — no validation data available.")
            return True

        final_loss = metrics.get('eval_loss')
        baseline_loss = self.config.evaluation.baseline_loss
        max_loss = self.config.evaluation.max_acceptable_loss

        # Handle missing or invalid eval_loss
        if final_loss is None:
            logger.warning("eval_loss not found in metrics. Skipping evaluation checks.")
            return True

        if math.isnan(final_loss) or math.isinf(final_loss):
            reason = f"eval_loss is {final_loss} (NaN or Inf) — training diverged."
            logger.error("EVALUATION FAILED: %s", reason)
            self._revert_model(final_path, reason)
            return False

        # Two independent checks:
        # 1) Hard ceiling (max_acceptable_loss)
        # 2) Regression vs baseline (baseline_loss)
        failed_reasons = []
        if max_loss is not None and final_loss > max_loss:
            failed_reasons.append(f"Final eval_loss ({final_loss:.4f}) exceeded max_acceptable_loss ({max_loss:.4f}).")
        if baseline_loss is not None and final_loss > baseline_loss:
            failed_reasons.append(f"Final eval_loss ({final_loss:.4f}) is worse than baseline ({baseline_loss:.4f}).")

        if failed_reasons:
            reason = " ".join(failed_reasons)
            logger.error("EVALUATION FAILED: %s", reason)
            self._revert_model(final_path, reason)
            return False

        # Log success with improvement details
        if baseline_loss is not None and baseline_loss > 0:
            improvement = ((baseline_loss - final_loss) / baseline_loss) * 100
            logger.info(
                "Evaluation passed: eval_loss=%.4f (%.1f%% improvement over baseline %.4f)",
                final_loss, improvement, baseline_loss
            )
        else:
            logger.info("Evaluation passed: eval_loss=%.4f", final_loss)

        return True

    def _revert_model(self, final_path: str, reason: str) -> None:
        """Delete generated model artifacts and notify."""
        logger.warning("Auto-revert enabled. Deleting generated artifacts at %s...", final_path)
        if os.path.exists(final_path):
            try:
                shutil.rmtree(final_path)
                logger.info("Reverted artifacts deleted successfully.")
            except OSError as e:
                logger.error(
                    "Failed to delete reverted artifacts at %s: %s. "
                    "Manual cleanup may be required.", final_path, e
                )

        self.notifier.notify_failure(
            run_name=self.run_name,
            reason=f"{reason} Adapters discarded."
        )

    def train(self, resume_from_checkpoint: Optional[str] = None) -> TrainResult:
        """Starts the main training loop. Returns TrainResult with status and metrics."""
        logger.info("Initializing TRL SFTTrainer...")
        self.notifier.notify_start(run_name=self.run_name)

        training_args = self._get_training_args()
        callbacks = [EarlyStoppingCallback(early_stopping_patience=3)]

        self.trainer = SFTTrainer(
            model=self.model,
            processing_class=self.tokenizer,
            args=training_args,
            train_dataset=self.dataset["train"],
            eval_dataset=self.dataset.get("validation", None),
            callbacks=callbacks
        )

        try:
            metrics: Dict[str, float] = {}

            # Baseline evaluation (base model, without adapters).
            # This enables Phase 2 "never overwrite a better model" behavior.
            if self.dataset.get("validation") and self.config.evaluation and self.config.evaluation.auto_revert:
                if self.config.evaluation.baseline_loss is None:
                    logger.info("Measuring baseline eval_loss (pre-training)...")
                    model_obj = self.trainer.model
                    baseline_metrics = None
                    # PEFT models often support disabling adapters for true base-model eval.
                    if hasattr(model_obj, "disable_adapter"):
                        try:
                            with model_obj.disable_adapter():
                                baseline_metrics = self.trainer.evaluate()
                        except Exception as e:
                            logger.warning(
                                "Failed to disable adapters for baseline eval, "
                                "evaluating with adapters instead: %s", e
                            )
                            baseline_metrics = self.trainer.evaluate()
                    else:
                        baseline_metrics = self.trainer.evaluate()
                    baseline_loss = baseline_metrics.get("eval_loss")
                    if baseline_loss is not None:
                        self.config.evaluation.baseline_loss = float(baseline_loss)
                        metrics["baseline_eval_loss"] = float(baseline_loss)
                        logger.info("Baseline eval_loss computed: %.4f", baseline_loss)
                    else:
                        logger.warning(
                            "Baseline evaluation completed but eval_loss not found in results. "
                            "Baseline regression check will be skipped."
                        )

            logger.info("Starting training...")
            hf_train_result = self.trainer.train(resume_from_checkpoint=resume_from_checkpoint)

            metrics.update(hf_train_result.metrics)
            if self.dataset.get("validation"):
                eval_metrics = self.trainer.evaluate()
                metrics.update(eval_metrics)

            final_path = os.path.join(
                self.checkpoint_dir,
                getattr(self.config.training, "final_model_dir", "final_model"),
            )
            self.save_final_model(final_path)

            # Autonomous Evaluation Check (loss-based)
            is_valid = self.execute_evaluation_checks(final_path, metrics)
            if not is_valid:
                return TrainResult(success=False, metrics=metrics, reverted=True)

            # Post-training benchmark evaluation (lm-eval-harness)
            benchmark_result = self._run_benchmark_if_configured(final_path, metrics)

            train_result = TrainResult(
                success=True,
                metrics=metrics,
                final_model_path=final_path,
            )

            if benchmark_result is not None:
                train_result.benchmark_scores = benchmark_result.scores
                train_result.benchmark_average = benchmark_result.average_score
                train_result.benchmark_passed = benchmark_result.passed

                # Add benchmark scores to metrics for webhook
                for task, score in benchmark_result.scores.items():
                    metrics[f"benchmark/{task}"] = score
                metrics["benchmark/average"] = benchmark_result.average_score

                if not benchmark_result.passed:
                    reason = benchmark_result.failure_reason or "Benchmark score below threshold."
                    self._revert_model(final_path, reason)
                    train_result.success = False
                    train_result.reverted = True
                    return train_result

            self.notifier.notify_success(run_name=self.run_name, metrics=metrics)
            return train_result

        except Exception as e:
            logger.exception("Training pipeline failed.")
            self.notifier.notify_failure(run_name=self.run_name, reason=str(e))
            raise

    def save_final_model(self, final_path: str) -> None:
        """Saves final artifacts (adapter-only by default)."""
        os.makedirs(final_path, exist_ok=True)
        merge_adapters = bool(getattr(self.config.training, "merge_adapters", False))

        # Prefer adapter-only save for PEFT models. This keeps artifacts small and makes revert safe.
        if not merge_adapters:
            logger.info("Saving final adapters to %s...", final_path)
            try:
                self.trainer.model.save_pretrained(final_path)
            except Exception as e:
                logger.warning(
                    "Direct model save failed, falling back to trainer.save_model: %s", e
                )
                self.trainer.save_model(final_path)
            self.tokenizer.save_pretrained(final_path)
            return

        # Optional: merge adapters into base weights and save a full model.
        logger.info("Merging adapters and saving full model to %s...", final_path)
        model_to_save = self.trainer.model
        try:
            merged = model_to_save.merge_and_unload()
            merged.save_pretrained(final_path, safe_serialization=True)
        except Exception as e:
            logger.warning(
                "Adapter merge failed, saving model state as-is: %s", e
            )
            self.trainer.save_model(final_path)
        self.tokenizer.save_pretrained(final_path)

    def _run_benchmark_if_configured(self, final_path: str, metrics: Dict[str, float]):
        """Run post-training benchmarks if configured. Returns BenchmarkResult or None."""
        eval_cfg = self.config.evaluation
        if not eval_cfg or not eval_cfg.benchmark or not eval_cfg.benchmark.enabled:
            return None

        bench_cfg = eval_cfg.benchmark
        if not bench_cfg.tasks:
            logger.warning("Benchmark enabled but no tasks specified. Skipping.")
            return None

        try:
            from .benchmark import run_benchmark
        except ImportError as e:
            logger.error(
                "Benchmark evaluation requested but lm-eval is not installed: %s. "
                "Install with: pip install forgelm[eval]", e
            )
            return None

        logger.info("Running post-training benchmark evaluation...")
        output_dir = bench_cfg.output_dir or os.path.join(self.checkpoint_dir, "benchmark")

        return run_benchmark(
            model=self.trainer.model,
            tokenizer=self.tokenizer,
            tasks=bench_cfg.tasks,
            num_fewshot=bench_cfg.num_fewshot,
            batch_size=bench_cfg.batch_size,
            limit=bench_cfg.limit,
            output_dir=output_dir,
            min_score=bench_cfg.min_score,
        )
