import torch
import os
from transformers import Trainer, TrainingArguments, DefaultDataCollator, EarlyStoppingCallback
from typing import Any, Dict

class ForgeTrainer:
    """Orchestrates the training process for ForgeLM using HuggingFace Trainer."""
    def __init__(self, model: Any, tokenizer: Any, config: Any, dataset: Dict[str, Any]):
        self.model = model
        self.tokenizer = tokenizer
        self.config = config
        self.dataset = dataset
        self.checkpoint_dir = self.config.training.output_dir
        
        os.makedirs(self.checkpoint_dir, exist_ok=True)
        
    def _get_training_args(self) -> TrainingArguments:
        return TrainingArguments(
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
            fp16=torch.cuda.is_available(),
            report_to="tensorboard"
        )
        
    def train(self) -> None:
        """Starts the main training loop."""
        print("Initializing HuggingFace Trainer...")
        training_args = self._get_training_args()
        
        callbacks = [EarlyStoppingCallback(early_stopping_patience=3)]
        
        self.trainer = Trainer(
            model=self.model,
            args=training_args,
            train_dataset=self.dataset["train"],
            eval_dataset=self.dataset.get("validation", None),
            data_collator=DefaultDataCollator(),
            callbacks=callbacks
        )
        
        print("Starting training...")
        self.trainer.train()
        
    def save_final_model(self, final_path: str = "./final_model") -> None:
        """Saves the final trained model weights and tokenizer."""
        print(f"Saving final model to {final_path}...")
        self.trainer.save_model(final_path)
        self.tokenizer.save_pretrained(final_path)
        print("Save complete.")
