import argparse
import json
import logging
import os
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

def _setup_logging(log_level: str, json_format: bool = False) -> None:
    """Configure structured logging for the entire forgelm package."""
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    if json_format:
        # Suppress human-readable logs when JSON output is requested
        numeric_level = logging.WARNING

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
        "--wizard",
        action="store_true",
        help="Launch interactive configuration wizard to generate a config.yaml."
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
        "--resume",
        type=str,
        nargs="?",
        const="auto",
        default=None,
        help="Resume training from a checkpoint. Use --resume for auto-detection or --resume /path/to/checkpoint."
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Air-gapped mode: disable all HF Hub network calls. Models and datasets must be available locally."
    )
    parser.add_argument(
        "--output-format",
        type=str,
        default="text",
        choices=["text", "json"],
        help="Output format for results (default: text). JSON mode outputs machine-readable results to stdout."
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set logging verbosity (default: INFO)."
    )
    return parser.parse_args()

def _run_dry_run(config: ForgeConfig, output_format: str) -> None:
    """Validate config, model access, and dataset access without loading heavy dependencies."""
    result = {
        "status": "valid",
        "model": config.model.name_or_path,
        "backend": config.model.backend,
        "load_in_4bit": config.model.load_in_4bit,
        "trust_remote_code": config.model.trust_remote_code,
        "dora": config.lora.use_dora,
        "lora_rank": config.lora.r,
        "lora_alpha": config.lora.alpha,
        "dataset": config.data.dataset_name_or_path,
        "epochs": config.training.num_train_epochs,
        "batch_size": config.training.per_device_train_batch_size,
        "output_dir": os.path.join(config.training.output_dir, config.training.final_model_dir),
        "offline": config.model.offline,
        "auto_revert": bool(config.evaluation and config.evaluation.auto_revert),
        "webhook_configured": bool(config.webhook and (config.webhook.url or config.webhook.url_env)),
    }

    if output_format == "json":
        print(json.dumps(result, indent=2))
        return

    logger.info("=== DRY RUN MODE ===")
    logger.info("Configuration validated successfully.")
    for key, value in result.items():
        if key == "status":
            continue
        logger.info("  %s: %s", key, value)

    if config.model.trust_remote_code:
        logger.warning("trust_remote_code is ENABLED — review model source before production use.")

    logger.info("=== DRY RUN COMPLETE — config is valid ===")

def _resolve_resume_checkpoint(checkpoint_dir: str, resume_arg: str) -> str:
    """Resolve the checkpoint path for --resume."""
    if resume_arg != "auto":
        if not os.path.isdir(resume_arg):
            logger.error("Checkpoint path does not exist: %s", resume_arg)
            sys.exit(EXIT_CONFIG_ERROR)
        return resume_arg

    # Auto-detect: find the latest checkpoint-* directory
    if not os.path.isdir(checkpoint_dir):
        logger.warning("No checkpoint directory found at %s. Starting fresh.", checkpoint_dir)
        return None

    checkpoint_dirs = sorted(
        [d for d in os.listdir(checkpoint_dir) if d.startswith("checkpoint-")],
        key=lambda x: int(x.split("-")[-1]) if x.split("-")[-1].isdigit() else 0,
    )

    if not checkpoint_dirs:
        logger.warning("No checkpoint-* directories found in %s. Starting fresh.", checkpoint_dir)
        return None

    latest = os.path.join(checkpoint_dir, checkpoint_dirs[-1])
    logger.info("Auto-detected checkpoint for resume: %s", latest)
    return latest

def _output_result(result, output_format: str) -> None:
    """Output training result in the requested format."""
    if output_format == "json":
        output = {
            "success": result.success,
            "metrics": result.metrics,
            "final_model_path": result.final_model_path,
            "reverted": result.reverted,
        }
        print(json.dumps(output, indent=2))
    else:
        if result.success:
            logger.info("ForgeLM Training Pipeline Completed Successfully!")
            if result.final_model_path:
                logger.info("Final model saved to: %s", result.final_model_path)
        else:
            if result.reverted:
                logger.error("ForgeLM Pipeline failed autonomous evaluation. Model was reverted.")
            else:
                logger.error("ForgeLM Pipeline failed.")

def main():
    args = parse_args()

    # --wizard mode: generate config interactively
    if args.wizard:
        from .wizard import run_wizard
        config_path = run_wizard()
        if config_path:
            # User chose to start training immediately — update args
            args.config = config_path
        else:
            sys.exit(EXIT_SUCCESS)

    # --config is required except for --version and --wizard (handled above)
    if not args.config:
        print("Error: --config is required. Use --help for usage.", file=sys.stderr)
        sys.exit(EXIT_CONFIG_ERROR)

    json_output = args.output_format == "json"
    _setup_logging(args.log_level, json_format=json_output)

    # 1. Load and validate configuration
    try:
        logger.info("Loading configuration from %s...", args.config)
        config = load_config(args.config)
    except FileNotFoundError as e:
        if json_output:
            print(json.dumps({"success": False, "error": f"Config file not found: {e}"}))
        else:
            logger.error("Configuration file not found: %s", e)
        sys.exit(EXIT_CONFIG_ERROR)
    except ConfigError as e:
        if json_output:
            print(json.dumps({"success": False, "error": str(e)}))
        else:
            logger.error("Configuration error: %s", e)
        sys.exit(EXIT_CONFIG_ERROR)
    except Exception as e:
        if json_output:
            print(json.dumps({"success": False, "error": f"Unexpected error: {e}"}))
        else:
            logger.error("Unexpected error loading configuration: %s", e)
        sys.exit(EXIT_CONFIG_ERROR)

    # 2. Apply --offline flag
    if args.offline:
        config.model.offline = True
    if config.model.offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_DATASETS_OFFLINE"] = "1"
        logger.info("Offline mode enabled. All HF Hub network calls are disabled.")

    # 3. Dry-run mode: validate and exit
    if args.dry_run:
        _run_dry_run(config, args.output_format)
        sys.exit(EXIT_SUCCESS)

    try:
        # Defer heavy imports so `--help`, `--version`, and `--dry-run` stay lightweight.
        from .data import prepare_dataset
        from .model import get_model_and_tokenizer
        from .trainer import ForgeTrainer
        from .utils import setup_authentication, manage_checkpoints

        # 4. Setup HF Authentication (skipped in offline mode)
        if not config.model.offline:
            setup_authentication(config.auth.hf_token if config.auth else None)
        else:
            logger.info("Skipping HF authentication (offline mode).")

        # 4. Model & Tokenizer
        model, tokenizer = get_model_and_tokenizer(config)

        # 5. Data Preprocessing
        dataset = prepare_dataset(config, tokenizer)

        # 6. Resolve checkpoint resume
        resume_checkpoint = None
        if args.resume:
            resume_checkpoint = _resolve_resume_checkpoint(
                config.training.output_dir, args.resume
            )

        # 7. Training
        trainer = ForgeTrainer(model=model, tokenizer=tokenizer, config=config, dataset=dataset)
        result = trainer.train(resume_from_checkpoint=resume_checkpoint)

        # 8. Checkpoint cleanup/compression
        logger.info("Cleaning up intermediate checkpoints...")
        manage_checkpoints(config.training.output_dir, action="keep")

        # 9. Output result
        _output_result(result, args.output_format)
        sys.exit(EXIT_SUCCESS if result.success else EXIT_EVAL_FAILURE)

    except ImportError as e:
        if json_output:
            print(json.dumps({"success": False, "error": f"Missing dependency: {e}"}))
        else:
            logger.error("Missing dependency: %s. Check your installation.", e)
        sys.exit(EXIT_TRAINING_ERROR)
    except Exception as e:
        if json_output:
            print(json.dumps({"success": False, "error": str(e)}))
        else:
            logger.exception("Training pipeline failed.")
        sys.exit(EXIT_TRAINING_ERROR)

if __name__ == "__main__":
    main()
