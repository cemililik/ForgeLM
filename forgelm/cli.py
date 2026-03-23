import argparse
import logging
import sys
from importlib.metadata import version as pkg_version, PackageNotFoundError
from .config import load_config, ForgeConfig, ConfigError

logger = logging.getLogger("forgelm.cli")

# Exit codes
EXIT_SUCCESS = 0
EXIT_CONFIG_ERROR = 1
EXIT_TRAINING_ERROR = 2
EXIT_EVAL_FAILURE = 3

def _get_version() -> str:
    try:
        return pkg_version("forgelm")
    except PackageNotFoundError:
        return "0.1.0-dev"

def _setup_logging(log_level: str) -> None:
    """Configure structured logging for the entire forgelm package."""
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

def parse_args():
    parser = argparse.ArgumentParser(description="ForgeLM: Language Model Fine-Tuning Toolkit")
    parser.add_argument(
        "--config",
        type=str,
        help="Path to the YAML configuration file."
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"ForgeLM {_get_version()}"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration and check model/dataset access without training."
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set logging verbosity (default: INFO)."
    )
    return parser.parse_args()

def _run_dry_run(config: ForgeConfig) -> None:
    """Validate config, model access, and dataset access without loading heavy dependencies."""
    logger.info("=== DRY RUN MODE ===")
    logger.info("Configuration validated successfully.")
    logger.info("  Model: %s", config.model.name_or_path)
    logger.info("  Backend: %s", config.model.backend)
    logger.info("  QLoRA 4-bit: %s", config.model.load_in_4bit)
    logger.info("  DoRA: %s", config.lora.use_dora)
    logger.info("  LoRA rank: %d, alpha: %d", config.lora.r, config.lora.alpha)
    logger.info("  Dataset: %s", config.data.dataset_name_or_path)
    logger.info("  Epochs: %d, Batch size: %d", config.training.num_train_epochs, config.training.per_device_train_batch_size)
    logger.info("  Output: %s/%s", config.training.output_dir, config.training.final_model_dir)

    if config.model.trust_remote_code:
        logger.warning("trust_remote_code is ENABLED — review model source before production use.")

    if config.evaluation and config.evaluation.auto_revert:
        logger.info("  Auto-revert: ENABLED (max_loss=%s)", config.evaluation.max_acceptable_loss)

    if config.webhook:
        webhook_url = config.webhook.url or (f"${config.webhook.url_env}" if config.webhook.url_env else None)
        logger.info("  Webhook: %s", webhook_url or "not configured")

    logger.info("=== DRY RUN COMPLETE — config is valid ===")

def main():
    args = parse_args()

    # --config is required except for --version (handled by argparse)
    if not args.config:
        print("Error: --config is required. Use --help for usage.", file=sys.stderr)
        sys.exit(EXIT_CONFIG_ERROR)

    _setup_logging(args.log_level)

    # 1. Load and validate configuration
    try:
        logger.info("Loading configuration from %s...", args.config)
        config = load_config(args.config)
    except FileNotFoundError as e:
        logger.error("Configuration file not found: %s", e)
        sys.exit(EXIT_CONFIG_ERROR)
    except ConfigError as e:
        logger.error("Configuration error: %s", e)
        sys.exit(EXIT_CONFIG_ERROR)
    except Exception as e:
        logger.error("Unexpected error loading configuration: %s", e)
        sys.exit(EXIT_CONFIG_ERROR)

    # 2. Dry-run mode: validate and exit
    if args.dry_run:
        _run_dry_run(config)
        sys.exit(EXIT_SUCCESS)

    try:
        # Defer heavy imports so `--help`, `--version`, and `--dry-run` stay lightweight.
        from .data import prepare_dataset
        from .model import get_model_and_tokenizer
        from .trainer import ForgeTrainer
        from .utils import setup_authentication, manage_checkpoints

        # 3. Setup HF Authentication
        setup_authentication(config.auth.hf_token if config.auth else None)

        # 4. Model & Tokenizer
        model, tokenizer = get_model_and_tokenizer(config)

        # 5. Data Preprocessing
        dataset = prepare_dataset(config, tokenizer)

        # 6. Training
        trainer = ForgeTrainer(model=model, tokenizer=tokenizer, config=config, dataset=dataset)
        is_successful = trainer.train()

        # 7. Checkpoint cleanup/compression
        logger.info("Cleaning up intermediate checkpoints...")
        manage_checkpoints(config.training.output_dir, action="keep")

        if is_successful:
            logger.info("ForgeLM Training Pipeline Completed Successfully!")
            sys.exit(EXIT_SUCCESS)
        else:
            logger.error("ForgeLM Pipeline failed autonomous evaluation. Model was reverted.")
            sys.exit(EXIT_EVAL_FAILURE)

    except ImportError as e:
        logger.error("Missing dependency: %s. Check your installation.", e)
        sys.exit(EXIT_TRAINING_ERROR)
    except Exception as e:
        logger.exception("Training pipeline failed.")
        sys.exit(EXIT_TRAINING_ERROR)

if __name__ == "__main__":
    main()
