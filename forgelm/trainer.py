import logging
import math
import os
import shutil
from typing import Any, Dict, Optional

import torch
from transformers import EarlyStoppingCallback
from trl import SFTConfig, SFTTrainer

from .results import TrainResult
from .webhook import WebhookNotifier

logger = logging.getLogger("forgelm.trainer")


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

        # Art. 12: Structured audit log
        from .compliance import AuditLogger

        self.audit = AuditLogger(self.checkpoint_dir)
        self.audit.log_event(
            "pipeline.initialized", model=config.model.name_or_path, trainer_type=config.training.trainer_type
        )

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

        # Warn if eval_steps is larger than training dataset
        train_size = len(self.dataset.get("train", []))
        if train_size > 0 and self.config.training.eval_steps > train_size:
            logger.warning(
                "eval_steps (%d) is larger than training dataset (%d samples). "
                "Evaluation will not run during training. Consider reducing eval_steps.",
                self.config.training.eval_steps,
                train_size,
            )

    @property
    def _trainer_type(self) -> str:
        return getattr(self.config.training, "trainer_type", "sft")

    def _get_common_training_kwargs(self) -> dict:
        """Return training arguments common to both SFT and ORPO."""
        kwargs = dict(
            output_dir=self.checkpoint_dir,
            max_steps=self.config.training.max_steps,
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
            gradient_checkpointing=torch.cuda.is_available(),
            optim="adamw_torch_fused" if torch.cuda.is_available() else "adamw_torch",
            bf16=torch.cuda.is_available() and torch.cuda.is_bf16_supported(),
            fp16=torch.cuda.is_available() and not torch.cuda.is_bf16_supported(),
            use_cpu=not torch.cuda.is_available(),
            report_to=getattr(self.config.training, "report_to", "tensorboard"),
            run_name=getattr(self.config.training, "run_name", None) or self.run_name,
        )

        # Inject distributed training configuration
        dist_cfg = self.config.distributed
        if dist_cfg and dist_cfg.strategy:
            self._apply_distributed_config(kwargs, dist_cfg)

        return kwargs

    def _apply_distributed_config(self, kwargs: dict, dist_cfg) -> None:
        """Apply DeepSpeed or FSDP configuration to training kwargs."""
        if dist_cfg.strategy == "deepspeed":
            ds_config = self._resolve_deepspeed_config(dist_cfg.deepspeed_config)
            kwargs["deepspeed"] = ds_config
            logger.info("DeepSpeed enabled with config: %s", dist_cfg.deepspeed_config or "auto")
            # DeepSpeed manages its own optimizer — remove gradient_checkpointing conflict
            kwargs["gradient_checkpointing"] = True

        elif dist_cfg.strategy == "fsdp":
            fsdp_options = [dist_cfg.fsdp_strategy]
            if dist_cfg.fsdp_auto_wrap:
                fsdp_options.append("auto_wrap")
            if dist_cfg.fsdp_offload:
                fsdp_options.append("offload")
            kwargs["fsdp"] = " ".join(fsdp_options)
            kwargs["fsdp_config"] = {
                "backward_prefetch": dist_cfg.fsdp_backward_prefetch,
                "state_dict_type": dist_cfg.fsdp_state_dict_type,
            }
            logger.info("FSDP enabled with strategy: %s", dist_cfg.fsdp_strategy)

        else:
            logger.warning("Unknown distributed strategy: %s. Ignoring.", dist_cfg.strategy)

    def _resolve_deepspeed_config(self, config_ref: str = None) -> str:
        """Resolve a DeepSpeed config reference to a file path.

        Accepts:
          - A preset name: "zero2", "zero3", "zero3_offload"
          - An absolute or relative file path to a JSON file
          - None: returns the default zero2 preset
        """
        presets = {
            "zero2": "configs/deepspeed/zero2.json",
            "zero3": "configs/deepspeed/zero3.json",
            "zero3_offload": "configs/deepspeed/zero3_offload.json",
        }

        if not config_ref:
            config_ref = "zero2"

        # Check if it's a preset name
        if config_ref in presets:
            # Resolve relative to the package installation or CWD
            preset_path = presets[config_ref]
            # Try package-relative first
            pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            full_path = os.path.join(pkg_dir, preset_path)
            if os.path.isfile(full_path):
                logger.info("Using DeepSpeed preset '%s': %s", config_ref, full_path)
                return full_path
            # Fall back to CWD
            if os.path.isfile(preset_path):
                return preset_path
            raise FileNotFoundError(
                f"DeepSpeed preset '{config_ref}' not found at {full_path}. "
                f"Ensure ForgeLM configs directory is accessible."
            )

        # It's a file path
        if os.path.isfile(config_ref):
            logger.info("Using custom DeepSpeed config: %s", config_ref)
            return config_ref

        raise FileNotFoundError(f"DeepSpeed config not found: {config_ref}")

    def _get_training_args_for_type(self):
        """Build the appropriate TRL config based on trainer_type."""
        tt = self._trainer_type
        kwargs = self._get_common_training_kwargs()

        if tt == "sft":
            kwargs["packing"] = bool(getattr(self.config.training, "packing", False))
            kwargs["dataset_text_field"] = "text"
            kwargs["max_seq_length"] = self.config.model.max_length
            return SFTConfig(**kwargs)

        elif tt == "orpo":
            from trl import ORPOConfig

            kwargs["beta"] = self.config.training.orpo_beta
            return ORPOConfig(**kwargs)

        elif tt == "dpo":
            from trl import DPOConfig

            kwargs["beta"] = self.config.training.dpo_beta
            return DPOConfig(**kwargs)

        elif tt == "simpo":
            from trl import CPOConfig

            # SimPO is implemented via CPOTrainer with loss_type="simpo" in TRL
            kwargs["beta"] = self.config.training.simpo_beta
            kwargs["cpo_alpha"] = 0.0  # pure SimPO (no NLL term)
            kwargs["simpo_gamma"] = self.config.training.simpo_gamma
            kwargs["loss_type"] = "simpo"
            return CPOConfig(**kwargs)

        elif tt == "kto":
            from trl import KTOConfig

            kwargs["beta"] = self.config.training.kto_beta
            return KTOConfig(**kwargs)

        elif tt == "grpo":
            from trl import GRPOConfig

            # GRPO generates responses during training — needs generation params
            kwargs["num_generations"] = self.config.training.grpo_num_generations
            kwargs["max_new_tokens"] = self.config.training.grpo_max_new_tokens
            # GRPO doesn't use load_best_model_at_end the same way
            kwargs.pop("load_best_model_at_end", None)
            kwargs.pop("metric_for_best_model", None)
            kwargs.pop("greater_is_better", None)
            return GRPOConfig(**kwargs)

        else:
            raise ValueError(f"Unknown trainer_type: {tt}")

    def execute_evaluation_checks(self, final_path: str, metrics: Dict[str, float]) -> bool:
        """Evaluates final loss against constraints. Returns True if acceptable, False if reverted."""
        if not self.config.evaluation or not self.config.evaluation.auto_revert:
            return True

        # No validation data means we can't evaluate
        if not self.dataset.get("validation"):
            logger.warning("Skipping evaluation checks — no validation data available.")
            return True

        final_loss = metrics.get("eval_loss")
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
                final_loss,
                improvement,
                baseline_loss,
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
                    "Failed to delete reverted artifacts at %s: %s. Manual cleanup may be required.", final_path, e
                )

        self.notifier.notify_failure(run_name=self.run_name, reason=f"{reason} Adapters discarded.")

    def train(self, resume_from_checkpoint: Optional[str] = None) -> TrainResult:
        """Starts the main training loop. Returns TrainResult with status and metrics."""
        self.notifier.notify_start(run_name=self.run_name)
        callbacks = []
        if self.dataset.get("validation"):
            patience = getattr(self.config.training, "early_stopping_patience", 3)
            callbacks.append(EarlyStoppingCallback(early_stopping_patience=patience))

        tt = self._trainer_type
        training_args = self._get_training_args_for_type()

        trainer_kwargs = dict(
            model=self.model,
            processing_class=self.tokenizer,
            args=training_args,
            train_dataset=self.dataset["train"],
            eval_dataset=self.dataset.get("validation", None),
            callbacks=callbacks,
        )

        if tt == "sft":
            logger.info("Initializing TRL SFTTrainer...")
            self.trainer = SFTTrainer(**trainer_kwargs)
        elif tt == "orpo":
            logger.info("Initializing TRL ORPOTrainer (ORPO preference alignment)...")
            from trl import ORPOTrainer

            self.trainer = ORPOTrainer(**trainer_kwargs)
        elif tt == "dpo":
            logger.info("Initializing TRL DPOTrainer (DPO preference alignment)...")
            from trl import DPOTrainer

            self.trainer = DPOTrainer(**trainer_kwargs)
        elif tt == "simpo":
            logger.info("Initializing TRL CPOTrainer (SimPO preference alignment)...")
            from trl import CPOTrainer

            self.trainer = CPOTrainer(**trainer_kwargs)
        elif tt == "kto":
            logger.info("Initializing TRL KTOTrainer (binary feedback alignment)...")
            from trl import KTOTrainer

            self.trainer = KTOTrainer(**trainer_kwargs)
        elif tt == "grpo":
            logger.info("Initializing TRL GRPOTrainer (reasoning RL)...")
            from trl import GRPOTrainer

            # GRPO doesn't use eval_dataset the same way — remove callbacks that depend on eval
            trainer_kwargs.pop("eval_dataset", None)
            trainer_kwargs["callbacks"] = []

            # Load reward model if configured
            reward_model_path = getattr(self.config.training, "grpo_reward_model", None)
            if reward_model_path:
                logger.info("Loading GRPO reward model: %s", reward_model_path)
                trainer_kwargs["reward_funcs"] = reward_model_path

            self.trainer = GRPOTrainer(**trainer_kwargs)
        else:
            raise ValueError(f"Unknown trainer_type: {tt}")

        try:
            metrics: Dict[str, float] = {}
            self.audit.log_event("training.started")

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
                                "Failed to disable adapters for baseline eval, evaluating with adapters instead: %s", e
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

                self.audit.log_event(
                    "benchmark.evaluation_completed",
                    passed=benchmark_result.passed,
                    average=benchmark_result.average_score,
                    scores=benchmark_result.scores,
                )

                if not benchmark_result.passed:
                    reason = benchmark_result.failure_reason or "Benchmark score below threshold."
                    self.audit.log_event("eval.revert_triggered", reason="benchmark", detail=reason)
                    self._revert_model(final_path, reason)
                    train_result.success = False
                    train_result.reverted = True
                    return train_result

            # Resource tracking + cost estimation
            train_result.resource_usage = self._collect_resource_usage()
            if train_result.resource_usage:
                for k, v in train_result.resource_usage.items():
                    if isinstance(v, (int, float)):
                        metrics[f"resource/{k}"] = v
                train_result.estimated_cost_usd = train_result.resource_usage.get("estimated_cost_usd")

            # Post-training safety evaluation
            safety_result = self._run_safety_if_configured(final_path)
            if safety_result is not None:
                train_result.safety_passed = safety_result.passed
                train_result.safety_score = safety_result.safety_score
                train_result.safety_categories = safety_result.category_distribution
                train_result.safety_severity = safety_result.severity_distribution
                train_result.safety_low_confidence = safety_result.low_confidence_count
                metrics["safety/safe_ratio"] = safety_result.safe_ratio
                if safety_result.safety_score is not None:
                    metrics["safety/safety_score"] = safety_result.safety_score
                self.audit.log_event(
                    "safety.evaluation_completed",
                    passed=safety_result.passed,
                    safe_ratio=safety_result.safe_ratio,
                    safety_score=safety_result.safety_score,
                    categories=safety_result.category_distribution,
                )
                if not safety_result.passed and self.config.evaluation and self.config.evaluation.auto_revert:
                    self.audit.log_event("eval.revert_triggered", reason="safety", detail=safety_result.failure_reason)
                    self._revert_model(final_path, safety_result.failure_reason or "Safety check failed.")
                    train_result.success = False
                    train_result.reverted = True
                    return train_result

            # LLM-as-Judge evaluation
            judge_result = self._run_judge_if_configured(final_path)
            if judge_result is not None:
                train_result.judge_score = judge_result.average_score
                train_result.judge_details = judge_result.details
                metrics["judge/average_score"] = judge_result.average_score
                self.audit.log_event(
                    "judge.evaluation_completed",
                    passed=judge_result.passed,
                    average_score=judge_result.average_score,
                )
                if not judge_result.passed and self.config.evaluation and self.config.evaluation.auto_revert:
                    self.audit.log_event("eval.revert_triggered", reason="judge", detail=judge_result.failure_reason)
                    self._revert_model(final_path, judge_result.failure_reason or "Judge score below threshold.")
                    train_result.success = False
                    train_result.reverted = True
                    return train_result

            # Generate model card
            self._generate_model_card(final_path, metrics, train_result)

            # Model integrity verification (Art. 15)
            self._generate_model_integrity(final_path)

            # Deployer instructions (Art. 13)
            self._generate_deployer_instructions(final_path, metrics)

            # Generate compliance artifacts (Art. 11 + Annex IV)
            self._export_compliance_if_needed(final_path, metrics, train_result)

            # Human approval gate (Art. 14)
            if self.config.evaluation and self.config.evaluation.require_human_approval:
                self.audit.log_event("human_approval.required", model_path=final_path)
                logger.info("Human approval required. Model saved to staging: %s", final_path)
                logger.info(
                    "Review results in %s/compliance/ and redeploy when ready. Run ID: %s",
                    self.checkpoint_dir,
                    self.audit.run_id,
                )
                train_result.success = True
                # Exit code 4 handled by CLI
                return train_result

            self.audit.log_event("pipeline.completed", success=True, metrics_summary=dict(list(metrics.items())[:5]))
            self.notifier.notify_success(run_name=self.run_name, metrics=metrics)
            return train_result

        except Exception as e:
            logger.exception("Training pipeline failed.")
            self.audit.log_event("pipeline.failed", error=str(e))
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
                logger.warning("Direct model save failed, falling back to trainer.save_model: %s", e)
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
            logger.warning("Adapter merge failed, saving model state as-is: %s", e)
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
                "Install with: pip install forgelm[eval]",
                e,
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

    def _generate_model_card(self, final_path: str, metrics: Dict[str, float], result: TrainResult) -> None:
        """Generate a HuggingFace-compatible model card."""
        try:
            from .model_card import generate_model_card

            generate_model_card(
                config=self.config,
                metrics=metrics,
                final_path=final_path,
                benchmark_scores=result.benchmark_scores,
                benchmark_average=result.benchmark_average,
                safety_score=result.safety_score,
                safety_categories=result.safety_categories,
            )
        except Exception as e:
            logger.warning("Failed to generate model card: %s", e)

    # Known GPU on-demand pricing ($/hour, approximate mid-2026 cloud averages)
    _GPU_PRICING = {
        # Consumer / Colab
        "Tesla T4": 0.35,
        "Tesla P100": 0.45,
        "Tesla V100": 1.00,
        "Tesla K80": 0.20,
        # Data center
        "NVIDIA A10G": 0.75,
        "NVIDIA A100-SXM4-40GB": 1.50,
        "NVIDIA A100-SXM4-80GB": 2.00,
        "NVIDIA A100 80GB PCIe": 2.00,
        "NVIDIA H100 80GB HBM3": 3.50,
        "NVIDIA H100 SXM5 80GB": 3.95,
        "NVIDIA H200": 4.50,
        "NVIDIA L4": 0.50,
        "NVIDIA L40S": 1.20,
        "NVIDIA B200": 5.00,
        # RTX (self-hosted, estimated electricity + amortization)
        "NVIDIA GeForce RTX 3090": 0.15,
        "NVIDIA GeForce RTX 4090": 0.20,
    }

    def _collect_resource_usage(self) -> Optional[Dict[str, Any]]:
        """Collect GPU resource usage metrics and estimate training cost."""
        usage = {}
        try:
            if torch.cuda.is_available():
                gpu_name = torch.cuda.get_device_name(0)
                usage["gpu_model"] = gpu_name
                usage["peak_vram_gb"] = round(torch.cuda.max_memory_allocated(0) / (1024**3), 2)
                usage["gpu_count"] = torch.cuda.device_count()
            # Training duration from HF Trainer
            log_history = getattr(self.trainer.state, "log_history", None)
            train_runtime = log_history[-1].get("train_runtime") if log_history else None
            if train_runtime:
                usage["training_duration_seconds"] = round(train_runtime, 1)
                gpu_count = usage.get("gpu_count", 1)
                gpu_hours = (train_runtime / 3600) * gpu_count
                usage["gpu_hours"] = round(gpu_hours, 3)

                # Cost estimation
                cost_per_hour = getattr(self.config.training, "gpu_cost_per_hour", None)
                if cost_per_hour is None:
                    gpu_name = usage.get("gpu_model", "")
                    cost_per_hour = self._GPU_PRICING.get(gpu_name)
                    if cost_per_hour:
                        usage["cost_source"] = "auto_detected"
                    else:
                        # Try partial match (GPU names vary across drivers)
                        for known_gpu, price in self._GPU_PRICING.items():
                            if known_gpu.lower() in gpu_name.lower() or gpu_name.lower() in known_gpu.lower():
                                cost_per_hour = price
                                usage["cost_source"] = "fuzzy_match"
                                break
                else:
                    usage["cost_source"] = "user_config"

                if cost_per_hour is not None:
                    usage["gpu_cost_per_hour_usd"] = cost_per_hour
                    estimated_cost = gpu_hours * cost_per_hour
                    usage["estimated_cost_usd"] = round(estimated_cost, 4)
                    logger.info(
                        "Estimated training cost: $%.4f (%.3f GPU-hours × $%.2f/hr)",
                        estimated_cost,
                        gpu_hours,
                        cost_per_hour,
                    )
        except Exception as e:
            logger.warning("Failed to collect resource usage: %s", e)
        return usage if usage else None

    def _run_safety_if_configured(self, final_path: str):
        """Run safety evaluation if configured. Returns SafetyResult or None."""
        eval_cfg = self.config.evaluation
        if not eval_cfg or not eval_cfg.safety or not eval_cfg.safety.enabled:
            return None

        try:
            from .safety import run_safety_evaluation
        except ImportError as e:
            logger.error("Safety evaluation import failed: %s", e)
            return None

        safety_cfg = eval_cfg.safety
        logger.info("Running post-training safety evaluation (scoring=%s)...", getattr(safety_cfg, "scoring", "binary"))
        output_dir = os.path.join(self.checkpoint_dir, "safety")
        return run_safety_evaluation(
            model=self.trainer.model,
            tokenizer=self.tokenizer,
            classifier_path=safety_cfg.classifier,
            test_prompts_path=safety_cfg.test_prompts,
            max_safety_regression=safety_cfg.max_safety_regression,
            output_dir=output_dir,
            scoring=getattr(safety_cfg, "scoring", "binary"),
            min_safety_score=getattr(safety_cfg, "min_safety_score", None),
            min_classifier_confidence=getattr(safety_cfg, "min_classifier_confidence", 0.7),
            track_categories=getattr(safety_cfg, "track_categories", False),
            severity_thresholds=getattr(safety_cfg, "severity_thresholds", None),
        )

    def _run_judge_if_configured(self, final_path: str):
        """Run LLM-as-Judge evaluation if configured. Returns JudgeResult or None."""
        eval_cfg = self.config.evaluation
        if not eval_cfg or not eval_cfg.llm_judge or not eval_cfg.llm_judge.enabled:
            return None

        try:
            from .judge import run_judge_evaluation
        except ImportError as e:
            logger.error("Judge evaluation import failed: %s", e)
            return None

        judge_cfg = eval_cfg.llm_judge
        api_key = os.getenv(judge_cfg.judge_api_key_env) if judge_cfg.judge_api_key_env else None
        logger.info("Running LLM-as-Judge evaluation (judge: %s)...", judge_cfg.judge_model)
        output_dir = os.path.join(self.checkpoint_dir, "judge")
        return run_judge_evaluation(
            model=self.trainer.model,
            tokenizer=self.tokenizer,
            eval_dataset_path=judge_cfg.eval_dataset,
            judge_model=judge_cfg.judge_model,
            judge_api_key=api_key,
            min_score=judge_cfg.min_score,
            output_dir=output_dir,
        )

    def _export_compliance_if_needed(self, final_path: str, metrics: Dict[str, float], result: TrainResult) -> None:
        """Export compliance artifacts if evaluation config is present."""
        try:
            from .compliance import export_compliance_artifacts, generate_training_manifest

            # Convert result objects to dicts for JSON serialization
            safety_dict = None
            if result.safety_passed is not None:
                safety_dict = {
                    "passed": result.safety_passed,
                    "safety_score": result.safety_score,
                    "categories": result.safety_categories,
                    "severity": result.safety_severity,
                    "low_confidence_count": result.safety_low_confidence,
                }
            judge_dict = None
            if result.judge_score is not None:
                judge_dict = {"average_score": result.judge_score}
            benchmark_dict = None
            if result.benchmark_scores is not None:
                benchmark_dict = {"scores": result.benchmark_scores, "average": result.benchmark_average}

            manifest = generate_training_manifest(
                config=self.config,
                metrics=metrics,
                resource_usage=result.resource_usage,
                safety_result=safety_dict,
                judge_result=judge_dict,
                benchmark_result=benchmark_dict,
            )
            compliance_dir = os.path.join(self.checkpoint_dir, "compliance")
            export_compliance_artifacts(manifest, self.config, compliance_dir)
            self.audit.log_event("compliance.artifacts_exported", directory=compliance_dir)
        except Exception as e:
            logger.warning("Failed to export compliance artifacts: %s", e)

    def _generate_model_integrity(self, final_path: str) -> None:
        """Art. 15: Generate SHA-256 checksums for all output artifacts."""
        try:
            from .compliance import generate_model_integrity

            integrity = generate_model_integrity(final_path)
            integrity_path = os.path.join(final_path, "model_integrity.json")
            import json

            with open(integrity_path, "w") as f:
                json.dump(integrity, f, indent=2)
            self.audit.log_event("model.integrity_verified", artifacts=len(integrity.get("artifacts", [])))
            logger.info("Model integrity checksums saved to %s", integrity_path)
        except Exception as e:
            logger.warning("Failed to generate model integrity: %s", e)

    def _generate_deployer_instructions(self, final_path: str, metrics: Dict[str, float]) -> None:
        """Art. 13: Generate deployer instructions document."""
        try:
            from .compliance import generate_deployer_instructions

            generate_deployer_instructions(self.config, metrics, final_path)
        except Exception as e:
            logger.warning("Failed to generate deployer instructions: %s", e)
