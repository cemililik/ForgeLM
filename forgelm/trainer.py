import torch
import os
import shutil
from trl import SFTTrainer, SFTConfig
from transformers import TrainingArguments, DefaultDataCollator, EarlyStoppingCallback
from typing import Any, Dict
from .webhook import WebhookNotifier

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
            
        final_loss = metrics.get('eval_loss', float('inf'))
        baseline_loss = self.config.evaluation.baseline_loss
        max_loss = self.config.evaluation.max_acceptable_loss

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
            print(f"❌ EVALUATION FAILED: {reason}")
            print("Auto-revert enabled. Deleting generated adapters...")
            if os.path.exists(final_path):
                shutil.rmtree(final_path)
            
            self.notifier.notify_failure(
                run_name=self.run_name, 
                reason=f"{reason} Adapters discarded."
            )
            return False
        return True
        
    def train(self) -> bool:
        """Starts the main training loop. Returns True if successful and valid."""
        print("Initializing TRL SFTTrainer...")
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
                    print("Measuring baseline eval_loss (pre-training)...")
                    model_obj = self.trainer.model
                    baseline_metrics = None
                    # PEFT models often support disabling adapters for true base-model eval.
                    if hasattr(model_obj, "disable_adapter"):
                        try:
                            with model_obj.disable_adapter():
                                baseline_metrics = self.trainer.evaluate()
                        except Exception:
                            baseline_metrics = self.trainer.evaluate()
                    else:
                        baseline_metrics = self.trainer.evaluate()
                    baseline_loss = baseline_metrics.get("eval_loss")
                    if baseline_loss is not None:
                        self.config.evaluation.baseline_loss = float(baseline_loss)
                        metrics["baseline_eval_loss"] = float(baseline_loss)

            print("Starting training...")
            train_result = self.trainer.train()
            
            metrics.update(train_result.metrics)
            if self.dataset.get("validation"):
                eval_metrics = self.trainer.evaluate()
                metrics.update(eval_metrics)
            
            final_path = os.path.join(
                self.checkpoint_dir,
                getattr(self.config.training, "final_model_dir", "final_model"),
            )
            self.save_final_model(final_path)
            
            # Autonomous Evaluation Check
            is_valid = self.execute_evaluation_checks(final_path, metrics)
            if is_valid:
                self.notifier.notify_success(run_name=self.run_name, metrics=metrics)
                return True
            else:
                return False
                
        except Exception as e:
            self.notifier.notify_failure(run_name=self.run_name, reason=str(e))
            raise e
        
    def save_final_model(self, final_path: str) -> None:
        """Saves final artifacts (adapter-only by default)."""
        os.makedirs(final_path, exist_ok=True)
        merge_adapters = bool(getattr(self.config.training, "merge_adapters", False))

        # Prefer adapter-only save for PEFT models. This keeps artifacts small and makes revert safe.
        if not merge_adapters:
            print(f"Saving final adapters to {final_path}...")
            try:
                self.trainer.model.save_pretrained(final_path)
            except Exception:
                # Fallback to trainer save_model behavior if model wrapper differs.
                self.trainer.save_model(final_path)
            self.tokenizer.save_pretrained(final_path)
            return

        # Optional: merge adapters into base weights and save a full model.
        print(f"Merging adapters and saving full model to {final_path}...")
        model_to_save = self.trainer.model
        try:
            merged = model_to_save.merge_and_unload()
            merged.save_pretrained(final_path, safe_serialization=True)
        except Exception:
            # If merge isn't supported, save best-effort model state.
            self.trainer.save_model(final_path)
        self.tokenizer.save_pretrained(final_path)
