import argparse
import sys
from .config import load_config
from .data import prepare_dataset
from .model import get_model_and_tokenizer
from .trainer import ForgeTrainer
from .utils import setup_authentication, manage_checkpoints

def parse_args():
    parser = argparse.ArgumentParser(description="ForgeLM: Language Model Fine-Tuning Toolkit")
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="Path to the YAML configuration file."
    )
    return parser.parse_args()

def main():
    args = parse_args()
    
    try:
        # 1. Load configuration
        print(f"Loading configuration from {args.config}...")
        config = load_config(args.config)
        
        # 2. Setup HF Authentication
        setup_authentication(config.auth.hf_token if config.auth else None)
        
        # 3. Model & Tokenizer
        model, tokenizer = get_model_and_tokenizer(config)
        
        # 4. Data Preprocessing
        dataset = prepare_dataset(config, tokenizer)
        
        # 5. Training
        trainer = ForgeTrainer(model=model, tokenizer=tokenizer, config=config, dataset=dataset)
        is_successful = trainer.train()
        
        # 6. Checkpoint cleanup/compression
        print("Cleaning up intermediate checkpoints...")
        manage_checkpoints(config.training.output_dir, action="keep") # Defaulting to keep for safety
        
        if is_successful:
            print("\n✅ ForgeLM Training Pipeline Completed Successfully!")
        else:
            print("\n❌ ForgeLM Pipeline failed autonomous evaluation. Model was reverted.")
            sys.exit(1)
        
    except Exception as e:
        print(f"\nError during training pipeline: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
