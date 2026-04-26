from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
from pathlib import Path

from .config import ConfigError, ForgeConfig, load_config

logger = logging.getLogger("forgelm.cli")

# Exit codes
EXIT_SUCCESS = 0
EXIT_CONFIG_ERROR = 1
EXIT_TRAINING_ERROR = 2
EXIT_EVAL_FAILURE = 3
EXIT_AWAITING_APPROVAL = 4


def _get_version() -> str:
    try:
        return pkg_version("forgelm")
    except PackageNotFoundError:
        from forgelm import __version__

        return __version__


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


def _add_common_subparser_flags(p: argparse.ArgumentParser, *, include_output_format: bool) -> None:
    """Register the shared --quiet / --log-level / --output-format flags.

    Uses ``default=argparse.SUPPRESS`` so an explicit flag at the main-parser
    level (before the subcommand) is not clobbered when the subparser fills
    in its own defaults.
    """
    if include_output_format:
        p.add_argument(
            "--output-format",
            type=str,
            default=argparse.SUPPRESS,
            choices=["text", "json"],
            help="Output format: text (default) or json.",
        )
    p.add_argument("-q", "--quiet", action="store_true", default=argparse.SUPPRESS, help="Suppress INFO logs.")
    p.add_argument(
        "--log-level",
        type=str,
        default=argparse.SUPPRESS,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set logging verbosity (default: INFO).",
    )


def _add_chat_subcommand(subparsers) -> None:
    p = subparsers.add_parser(
        "chat",
        help="Interactive chat REPL with a fine-tuned model.",
        description=(
            "Load a fine-tuned model and start an interactive terminal session.  "
            "Supports streaming output, slash commands (/reset, /save, /temperature, "
            "/system, /exit), and optional per-response safety annotations."
        ),
    )
    p.add_argument("model_path", help="Path to a saved HuggingFace model directory or HF Hub ID.")
    p.add_argument("--adapter", type=str, default=None, help="PEFT adapter directory to merge before chat.")
    p.add_argument("--system", type=str, default=None, metavar="PROMPT", help="Initial system prompt.")
    p.add_argument("--temperature", type=float, default=0.7, help="Sampling temperature (default: 0.7).")
    p.add_argument("--max-new-tokens", type=int, default=512, help="Max tokens per response (default: 512).")
    p.add_argument("--no-stream", action="store_true", help="Disable streaming output.")
    p.add_argument("--load-in-4bit", action="store_true", help="Load model in 4-bit NF4 quantisation.")
    p.add_argument("--load-in-8bit", action="store_true", help="Load model in 8-bit quantisation.")
    p.add_argument("--trust-remote-code", action="store_true", help="Allow execution of model-bundled code.")
    p.add_argument(
        "--backend",
        type=str,
        default="transformers",
        choices=["transformers", "unsloth"],
        help="Model backend (default: transformers).",
    )
    # chat is interactive; --output-format doesn't apply.
    _add_common_subparser_flags(p, include_output_format=False)


def _add_export_subcommand(subparsers) -> None:
    p = subparsers.add_parser(
        "export",
        help="Export a fine-tuned model to GGUF format.",
        description=(
            "Convert a HuggingFace model to GGUF for use with Ollama, llama.cpp, "
            "and compatible runtimes.  Requires: pip install 'forgelm[export]'"
        ),
    )
    p.add_argument("model_path", help="Path to a saved HuggingFace model directory.")
    p.add_argument("--output", type=str, required=True, metavar="FILE", help="Output .gguf file path.")
    p.add_argument(
        "--format",
        type=str,
        default="gguf",
        choices=["gguf"],
        help="Export format (default: gguf).",
    )
    p.add_argument(
        "--quant",
        type=str,
        default="q4_k_m",
        choices=["q2_k", "q3_k_m", "q4_k_m", "q5_k_m", "q8_0", "f16"],
        help="Quantisation type (default: q4_k_m).",
    )
    p.add_argument("--adapter", type=str, default=None, help="PEFT adapter directory to merge before export.")
    p.add_argument(
        "--no-integrity-update",
        action="store_true",
        help="Skip updating model_integrity.json with the exported artifact.",
    )
    _add_common_subparser_flags(p, include_output_format=True)


def _add_deploy_subcommand(subparsers) -> None:
    p = subparsers.add_parser(
        "deploy",
        help="Generate a deployment configuration for a serving runtime.",
        description=(
            "Produce a ready-to-use config file for Ollama, vLLM, TGI, or "
            "HuggingFace Inference Endpoints.  Does not start a server."
        ),
    )
    p.add_argument("model_path", help="Path to a saved HuggingFace model directory or HF Hub ID.")
    p.add_argument(
        "--target",
        type=str,
        required=True,
        choices=["ollama", "vllm", "tgi", "hf-endpoints"],
        help="Target serving runtime.",
    )
    p.add_argument("--output", type=str, default=None, metavar="FILE", help="Output file path (default: auto).")
    p.add_argument("--system", type=str, default=None, metavar="PROMPT", help="System prompt (Ollama only).")
    p.add_argument("--max-length", type=int, default=4096, help="Context window length (default: 4096).")
    p.add_argument(
        "--gpu-memory-utilization",
        type=float,
        default=0.90,
        help="vLLM GPU memory utilisation fraction (default: 0.90).",
    )
    p.add_argument("--port", type=int, default=8080, help="Host port for TGI container (default: 8080).")
    p.add_argument("--trust-remote-code", action="store_true", help="Set trust_remote_code in vLLM config.")
    p.add_argument(
        "--vendor",
        type=str,
        default="aws",
        help="Cloud vendor for HF Endpoints config (default: aws).",
    )
    _add_common_subparser_flags(p, include_output_format=True)


def _add_quickstart_subcommand(subparsers) -> None:
    p = subparsers.add_parser(
        "quickstart",
        help="Generate a config from a curated template (and optionally start training).",
        description=(
            "Pick a template (e.g. customer-support, code-assistant), get a working YAML and "
            "(optionally) seed dataset out the other end. The generated config uses the same "
            "schema as a hand-written one — quickstart is just opinionated defaults plus a "
            "license-clean seed dataset."
        ),
    )
    p.add_argument(
        "template",
        nargs="?",
        default=None,
        help="Template name. Run with --list to see what's available.",
    )
    p.add_argument("--list", action="store_true", help="List available templates and exit.")
    p.add_argument(
        "--model",
        type=str,
        default=None,
        metavar="MODEL_ID",
        help="Override the template's primary model (HF Hub ID or local path).",
    )
    p.add_argument(
        "--dataset",
        type=str,
        default=None,
        metavar="PATH",
        help="Override the template's bundled dataset (HF Hub ID or local JSONL path).",
    )
    p.add_argument(
        "--output",
        type=str,
        default=None,
        metavar="FILE",
        help="Where to write the generated YAML (default: ./configs/<template>-<timestamp>.yaml).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate the config and print next steps; do not invoke training.",
    )
    p.add_argument(
        "--no-chat",
        action="store_true",
        help="When training succeeds, do NOT auto-launch `forgelm chat` afterwards.",
    )
    _add_common_subparser_flags(p, include_output_format=True)


def parse_args():
    parser = argparse.ArgumentParser(
        description="ForgeLM: Language Model Fine-Tuning Toolkit",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Subcommands:\n"
            "  forgelm quickstart [TEMPLATE]   Generate a config from a curated template\n"
            "  forgelm chat MODEL_PATH         Interactive chat REPL\n"
            "  forgelm export MODEL_PATH       Export model to GGUF\n"
            "  forgelm deploy MODEL_PATH       Generate serving config\n"
            "\nRun 'forgelm <subcommand> --help' for subcommand details."
        ),
    )

    # --- Subcommand router (dest=command; None when not given → training mode) ---
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    _add_chat_subcommand(subparsers)
    _add_export_subcommand(subparsers)
    _add_deploy_subcommand(subparsers)
    _add_quickstart_subcommand(subparsers)

    # --- Top-level flags (training / config-driven mode) ---
    parser.add_argument("--config", type=str, help="Path to the YAML configuration file.")
    parser.add_argument(
        "--wizard", action="store_true", help="Launch interactive configuration wizard to generate a config.yaml."
    )
    parser.add_argument("--version", action="version", version=f"ForgeLM {_get_version()}")
    parser.add_argument(
        "--dry-run", action="store_true", help="Validate configuration and check model/dataset access without training."
    )
    parser.add_argument(
        "--fit-check",
        action="store_true",
        help=(
            "Estimate peak training VRAM from the config without loading the model.  "
            "Requires --config.  Prints a FITS / TIGHT / OOM verdict with a breakdown."
        ),
    )
    parser.add_argument(
        "--resume",
        type=str,
        nargs="?",
        const="auto",
        default=None,
        help="Resume training from a checkpoint. Use --resume for auto-detection or --resume /path/to/checkpoint.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Air-gapped mode: disable all HF Hub network calls. Models and datasets must be available locally.",
    )
    parser.add_argument(
        "--benchmark-only",
        type=str,
        default=None,
        metavar="MODEL_PATH",
        help="Run benchmark evaluation on an existing model without training. Requires evaluation.benchmark config.",
    )
    parser.add_argument(
        "--merge", action="store_true", help="Run model merging from the merge section of your config. No training."
    )
    parser.add_argument(
        "--output-format",
        type=str,
        default="text",
        choices=["text", "json"],
        help="Output format for results (default: text). JSON mode outputs machine-readable results to stdout.",
    )
    parser.add_argument(
        "--generate-data",
        action="store_true",
        help="Generate synthetic training data using teacher model. No training.",
    )
    parser.add_argument(
        "--compliance-export",
        type=str,
        default=None,
        metavar="OUTPUT_DIR",
        help="Export compliance artifacts (audit trail, provenance) from an existing training run.",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress INFO logs. Only show warnings and errors.",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Set logging verbosity (default: INFO).",
    )
    return parser.parse_args()


def _galore_dry_run_fields(config: ForgeConfig) -> dict:
    if not config.training.galore_enabled:
        return {"galore_enabled": False, "galore_optim": None, "galore_rank": None}
    return {
        "galore_enabled": True,
        "galore_optim": config.training.galore_optim,
        "galore_rank": config.training.galore_rank,
    }


def _evaluation_dry_run_fields(config: ForgeConfig) -> dict:
    eval_cfg = config.evaluation
    safety = eval_cfg.safety if eval_cfg else None
    return {
        "auto_revert": bool(eval_cfg and eval_cfg.auto_revert),
        "safety_enabled": bool(safety and safety.enabled),
        "safety_scoring": safety.scoring if safety else None,
    }


def _compliance_dry_run_fields(config: ForgeConfig) -> dict:
    comp = config.compliance
    return {
        "compliance_configured": bool(comp and comp.provider_name),
        "risk_classification": comp.risk_classification if comp else None,
    }


def _build_dry_run_result(config: ForgeConfig) -> dict:
    """Assemble the dry-run summary dict from the validated config."""
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
        "distributed": config.distributed.strategy if config.distributed else None,
        "rope_scaling": config.training.rope_scaling,
        "neftune_noise_alpha": config.training.neftune_noise_alpha,
        "webhook_configured": bool(config.webhook and (config.webhook.url or config.webhook.url_env)),
    }
    result.update(_galore_dry_run_fields(config))
    result.update(_evaluation_dry_run_fields(config))
    result.update(_compliance_dry_run_fields(config))
    return result


def _run_dry_run(config: ForgeConfig, output_format: str) -> None:
    """Validate config, model access, and dataset access without loading heavy dependencies."""
    result = _build_dry_run_result(config)

    if output_format == "json":
        print(json.dumps(result, indent=2))
        return

    logger.info("=== DRY RUN MODE ===")
    logger.info("Configuration validated successfully.")
    for key, value in result.items():
        if key != "status":
            logger.info("  %s: %s", key, value)

    if config.model.trust_remote_code:
        logger.warning("trust_remote_code is ENABLED — review model source before production use.")

    logger.info("=== DRY RUN COMPLETE — config is valid ===")


def _run_benchmark_only(config: ForgeConfig, model_path: str, output_format: str) -> None:
    """Run benchmark evaluation on an existing model without training."""
    from .benchmark import run_benchmark
    from .model import get_model_and_tokenizer

    eval_cfg = config.evaluation
    if not eval_cfg or not eval_cfg.benchmark or not eval_cfg.benchmark.tasks:
        logger.error("No benchmark tasks configured. Add evaluation.benchmark.tasks to your config.")
        sys.exit(EXIT_CONFIG_ERROR)

    bench_cfg = eval_cfg.benchmark

    # Override model path to the provided one
    config.model.name_or_path = model_path
    logger.info("Loading model from %s for benchmark evaluation...", model_path)

    model, tokenizer = get_model_and_tokenizer(config)

    output_dir = bench_cfg.output_dir or os.path.join(os.path.dirname(model_path), "benchmark")

    result = run_benchmark(
        model=model,
        tokenizer=tokenizer,
        tasks=bench_cfg.tasks,
        num_fewshot=bench_cfg.num_fewshot,
        batch_size=bench_cfg.batch_size,
        limit=bench_cfg.limit,
        output_dir=output_dir,
        min_score=bench_cfg.min_score,
    )

    if output_format == "json":
        output = {
            "success": result.passed,
            "model_path": model_path,
            "benchmark": {
                "scores": result.scores,
                "average": result.average_score,
                "passed": result.passed,
            },
        }
        if result.failure_reason:
            output["failure_reason"] = result.failure_reason
        print(json.dumps(output, indent=2))
    else:
        logger.info("Benchmark Results:")
        for task, score in result.scores.items():
            logger.info("  %s: %.4f", task, score)
        logger.info("  Average: %.4f", result.average_score)
        if result.passed:
            logger.info("Benchmark evaluation PASSED.")
        else:
            logger.error("Benchmark evaluation FAILED: %s", result.failure_reason)

    if not result.passed:
        sys.exit(EXIT_EVAL_FAILURE)


def _run_merge(config: ForgeConfig, output_format: str) -> None:
    """Run model merging from config without training."""
    if not config.merge or not config.merge.enabled:
        logger.error("No merge configuration found or merge not enabled. Add a 'merge' section to your config.")
        sys.exit(EXIT_CONFIG_ERROR)

    from .merging import merge_peft_adapters

    result = merge_peft_adapters(
        base_model_path=config.model.name_or_path,
        adapters=config.merge.models,
        method=config.merge.method,
        output_dir=config.merge.output_dir,
        trust_remote_code=config.model.trust_remote_code,
    )

    if output_format == "json":
        print(
            json.dumps(
                {
                    "success": result.success,
                    "method": result.method,
                    "num_models": result.num_models,
                    "output_dir": result.output_dir,
                    "error": result.error,
                },
                indent=2,
            )
        )
    else:
        if result.success:
            logger.info(
                "Model merge completed: %d models merged with '%s' → %s",
                result.num_models,
                result.method,
                result.output_dir,
            )
        else:
            logger.error("Model merge failed: %s", result.error)

    if not result.success:
        sys.exit(EXIT_TRAINING_ERROR)


def _run_generate_data(config: ForgeConfig, output_format: str) -> None:
    """Generate synthetic training data using teacher model."""
    from .synthetic import SyntheticDataGenerator

    if not config.synthetic or not config.synthetic.enabled:
        logger.error("Synthetic data generation not configured. Add 'synthetic' section to config.")
        sys.exit(EXIT_CONFIG_ERROR)

    generator = SyntheticDataGenerator(config)
    result = generator.generate()

    if output_format == "json":
        print(
            json.dumps(
                {
                    "success": result.successful > 0,
                    "total_prompts": result.total_prompts,
                    "successful": result.successful,
                    "failed": result.failed,
                    "success_rate": round(result.success_rate, 4),
                    "output_file": result.output_file,
                    "duration_seconds": round(result.duration_seconds, 2),
                    "errors": result.errors[:10],
                },
                indent=2,
            )
        )
    else:
        logger.info(
            "Synthetic data generation: %d/%d successful (%.1f%%) → %s",
            result.successful,
            result.total_prompts,
            result.success_rate * 100,
            result.output_file,
        )

    if result.successful == 0:
        sys.exit(EXIT_TRAINING_ERROR)


def _run_compliance_export(config: ForgeConfig, output_dir: str, output_format: str) -> None:
    """Generate compliance artifacts from config without training."""
    from .compliance import export_compliance_artifacts, generate_training_manifest

    logger.info("Generating compliance artifacts to %s...", output_dir)
    manifest = generate_training_manifest(config=config, metrics={})
    files = export_compliance_artifacts(manifest, output_dir)

    if output_format == "json":
        print(json.dumps({"success": True, "files": files, "output_dir": output_dir}, indent=2))
    else:
        logger.info("Compliance artifacts exported:")
        for f in files:
            logger.info("  %s", f)


def _resolve_resume_checkpoint(checkpoint_dir: str, resume_arg: str) -> str | None:
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
        if result.benchmark_scores is not None:
            output["benchmark"] = {
                "scores": result.benchmark_scores,
                "average": result.benchmark_average,
                "passed": result.benchmark_passed,
            }
        if result.resource_usage:
            output["resource_usage"] = result.resource_usage
        if result.estimated_cost_usd is not None:
            output["estimated_cost_usd"] = result.estimated_cost_usd
        if result.safety_passed is not None:
            output["safety"] = {
                "passed": result.safety_passed,
                "safety_score": result.safety_score,
                "categories": result.safety_categories,
                "severity": result.safety_severity,
                "low_confidence_count": result.safety_low_confidence,
            }
        if result.judge_score is not None:
            output["judge"] = {
                "average_score": result.judge_score,
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

        # Print cost estimation in text mode
        if result.estimated_cost_usd is not None:
            logger.info("Estimated training cost: $%.4f", result.estimated_cost_usd)
            if result.resource_usage:
                gpu_hours = result.resource_usage.get("gpu_hours")
                cost_source = result.resource_usage.get("cost_source", "unknown")
                if gpu_hours:
                    logger.info("  GPU-hours: %.3f (pricing: %s)", gpu_hours, cost_source)

        # Print benchmark results in text mode
        if result.benchmark_scores:
            logger.info("Benchmark Results:")
            for task, score in result.benchmark_scores.items():
                logger.info("  %s: %.4f", task, score)
            if result.benchmark_average is not None:
                logger.info("  Average: %.4f", result.benchmark_average)


def _run_fit_check(config: ForgeConfig, output_format: str) -> None:
    """Estimate peak training VRAM from config without loading the model."""
    from .fit_check import estimate_vram, format_fit_check

    result = estimate_vram(config)

    if output_format == "json":
        print(
            json.dumps(
                {
                    "verdict": result.verdict,
                    "estimated_gb": result.estimated_gb,
                    "available_gb": result.available_gb,
                    "hypothetical": result.hypothetical,
                    "breakdown": result.breakdown,
                    "recommendations": result.recommendations,
                },
                indent=2,
            )
        )
        return

    print(format_fit_check(result))


def _run_chat_cmd(args) -> None:
    """Dispatch the ``forgelm chat`` subcommand."""
    try:
        from .chat import run_chat

        run_chat(
            model_path=args.model_path,
            adapter=args.adapter,
            system_prompt=args.system,
            temperature=args.temperature,
            max_new_tokens=args.max_new_tokens,
            stream=not args.no_stream,
            load_in_4bit=args.load_in_4bit,
            load_in_8bit=args.load_in_8bit,
            trust_remote_code=args.trust_remote_code,
            backend=args.backend,
        )
    except ImportError as e:
        logger.error("Missing dependency for chat: %s", e)
        sys.exit(EXIT_TRAINING_ERROR)
    except Exception as e:
        logger.exception("Chat session failed: %s", e)
        sys.exit(EXIT_TRAINING_ERROR)


def _run_export_cmd(args, output_format: str) -> None:
    """Dispatch the ``forgelm export`` subcommand."""
    from .export import export_model

    result = export_model(
        model_path=args.model_path,
        output_path=args.output,
        output_format=args.format,
        quant=args.quant,
        adapter=args.adapter,
        update_integrity=not args.no_integrity_update,
    )

    if output_format == "json":
        print(
            json.dumps(
                {
                    "success": result.success,
                    "output_path": result.output_path,
                    "format": result.format,
                    "quant": result.quant,
                    "sha256": result.sha256,
                    "size_bytes": result.size_bytes,
                    "error": result.error,
                },
                indent=2,
            )
        )
    else:
        if result.success:
            logger.info(
                "Export complete: %s (quant=%s, sha256=%s…)",
                result.output_path,
                result.quant,
                (result.sha256 or "")[:12],
            )
        else:
            logger.error("Export failed: %s", result.error)

    if not result.success:
        sys.exit(EXIT_TRAINING_ERROR)


def _run_deploy_cmd(args, output_format: str) -> None:
    """Dispatch the ``forgelm deploy`` subcommand."""
    from .deploy import HFEndpointsOptions, generate_deploy_config

    result = generate_deploy_config(
        model_path=args.model_path,
        target=args.target,
        output_path=args.output,
        system_prompt=args.system,
        max_length=args.max_length,
        trust_remote_code=args.trust_remote_code,
        gpu_memory_utilization=args.gpu_memory_utilization,
        port=args.port,
        hf_endpoints=HFEndpointsOptions(vendor=getattr(args, "vendor", "aws")),
    )

    if output_format == "json":
        print(
            json.dumps(
                {
                    "success": result.success,
                    "target": result.target,
                    "output_path": result.output_path,
                    "error": result.error,
                },
                indent=2,
            )
        )
    else:
        if result.success:
            logger.info("Deploy config written: %s (target=%s)", result.output_path, result.target)
        else:
            logger.error("Deploy config generation failed: %s", result.error)

    if not result.success:
        sys.exit(EXIT_TRAINING_ERROR)


def _run_quickstart_cmd(args, output_format: str) -> None:
    """Dispatch the ``forgelm quickstart`` subcommand.

    Three flows: ``--list`` (print templates and exit); plain
    ``forgelm quickstart TEMPLATE`` (generate config + auto-train + auto-chat);
    ``--dry-run`` (generate config, print next step, do not train).
    """
    from .quickstart import format_template_list, run_quickstart, summarize_result

    if args.list:
        if output_format == "json":
            from .quickstart import list_templates as _list

            payload = [
                {
                    "name": t.name,
                    "title": t.title,
                    "description": t.description,
                    "primary_model": t.primary_model,
                    "fallback_model": t.fallback_model,
                    "trainer_type": t.trainer_type,
                    "estimated_minutes": t.estimated_minutes,
                    "min_vram_for_primary_gb": t.min_vram_for_primary_gb,
                    "bundled_dataset": t.bundled_dataset,
                    "license_note": t.license_note,
                }
                for t in _list()
            ]
            print(json.dumps(payload, indent=2))
        else:
            print(format_template_list())
        sys.exit(EXIT_SUCCESS)

    if not args.template:
        logger.error("forgelm quickstart: TEMPLATE is required (or pass --list to see the menu).")
        sys.exit(EXIT_CONFIG_ERROR)

    try:
        result = run_quickstart(
            args.template,
            model_override=args.model,
            dataset_override=args.dataset,
            output_path=args.output,
            dry_run=args.dry_run,
        )
    except (FileNotFoundError, ValueError) as e:
        if output_format == "json":
            print(json.dumps({"success": False, "error": str(e)}))
        else:
            logger.error("Quickstart failed: %s", e)
        sys.exit(EXIT_CONFIG_ERROR)

    if output_format == "json":
        print(
            json.dumps(
                {
                    "success": True,
                    "template": result.template.name,
                    "config_path": str(result.config_path),
                    "model": result.chosen_model,
                    "dataset": result.dataset_path,
                    "selection_reason": result.selection_reason,
                    "dry_run": result.dry_run,
                    "notes": result.extra_notes,
                },
                indent=2,
            )
        )
    else:
        print(summarize_result(result))

    if result.dry_run:
        sys.exit(EXIT_SUCCESS)

    # Spec: invoke training automatically. Use a subprocess so each phase keeps
    # its own clean process state and Ctrl-C is honoured cleanly.
    #
    # Security: argv-list form (not shell=True) and sys.executable as argv[0]
    # mean no shell is invoked — meta characters in `result.config_path` are
    # passed verbatim to the child as a single argument, with no expansion.
    import subprocess  # nosec B404 — argv-list usage only; see comment above

    train_cmd = [sys.executable, "-m", "forgelm.cli", "--config", str(result.config_path)]
    logger.info("Starting training: %s", " ".join(train_cmd))
    train_rc = subprocess.run(train_cmd, check=False).returncode  # noqa: S603  # nosec B603
    if train_rc != 0:
        logger.error("Training exited with code %d", train_rc)
        sys.exit(train_rc)

    if args.no_chat:
        sys.exit(EXIT_SUCCESS)

    # Auto-launch chat against the trained model. Mirror the trainer's output_dir
    # convention from the bundled config.
    final_model_dir = Path(_load_config_for_quickstart_chat(result.config_path)) / "final_model"
    if not final_model_dir.is_dir():
        logger.warning(
            "Skipping auto-chat: trained model directory not found at %s. Run `forgelm chat <model_path>` manually.",
            final_model_dir,
        )
        sys.exit(EXIT_SUCCESS)

    chat_cmd = [sys.executable, "-m", "forgelm.cli", "chat", str(final_model_dir)]
    logger.info("Launching chat REPL: %s", " ".join(chat_cmd))
    subprocess.run(chat_cmd, check=False)  # noqa: S603  # nosec B603
    sys.exit(EXIT_SUCCESS)


def _load_config_for_quickstart_chat(config_path: Path) -> str:
    """Read the generated YAML and return the training output_dir.

    Kept tiny + standalone so quickstart never has to import the heavy config
    validation pipeline just to find the trained checkpoint directory.
    """
    import yaml

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    training = cfg.get("training", {}) or {}
    return training.get("output_dir", "./checkpoints")


def _dispatch_subcommand(command: str, args) -> None:
    """Run a Phase 10/10.5 subcommand (chat / export / deploy / quickstart) and exit."""
    if command == "chat":
        # _run_chat_cmd's REPL catches KeyboardInterrupt internally for the
        # input prompt; this outer guard covers Ctrl-C during model load /
        # welcome banner render, before the REPL loop has started.
        try:
            _run_chat_cmd(args)
        except KeyboardInterrupt:
            pass
        sys.exit(EXIT_SUCCESS)
    elif command == "export":
        _run_export_cmd(args, getattr(args, "output_format", "text"))
        sys.exit(EXIT_SUCCESS)
    elif command == "deploy":
        _run_deploy_cmd(args, getattr(args, "output_format", "text"))
        sys.exit(EXIT_SUCCESS)
    elif command == "quickstart":
        try:
            _run_quickstart_cmd(args, getattr(args, "output_format", "text"))
        except KeyboardInterrupt:
            pass
        sys.exit(EXIT_SUCCESS)


def _maybe_run_wizard(args) -> None:
    """Open the interactive wizard when --wizard was passed; mutates *args*."""
    if not args.wizard:
        return
    from .wizard import run_wizard

    config_path = run_wizard()
    if config_path:
        args.config = config_path
    else:
        sys.exit(EXIT_SUCCESS)


def _load_config_or_exit(config_path: str, json_output: bool):
    """Load config and translate exceptions into the right exit code."""
    try:
        logger.info("Loading configuration from %s...", config_path)
        return load_config(config_path)
    except FileNotFoundError as e:
        msg = f"Config file not found: {e}"
    except ConfigError as e:
        msg = str(e)
    except Exception as e:
        msg = f"Unexpected error: {e}"
    if json_output:
        print(json.dumps({"success": False, "error": msg}))
    else:
        logger.error("Configuration error: %s", msg)
    sys.exit(EXIT_CONFIG_ERROR)


def _apply_offline_flag(config, offline_arg: bool) -> None:
    if offline_arg:
        config.model.offline = True
    if config.model.offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_DATASETS_OFFLINE"] = "1"
        logger.info("Offline mode enabled. All HF Hub network calls are disabled.")


def _maybe_run_no_train_mode(config, args) -> None:
    """If a non-training mode flag is set, run it and exit."""
    if args.dry_run:
        _run_dry_run(config, args.output_format)
        sys.exit(EXIT_SUCCESS)
    if args.fit_check:
        _run_fit_check(config, args.output_format)
        sys.exit(EXIT_SUCCESS)
    if args.benchmark_only:
        _run_benchmark_only(config, args.benchmark_only, args.output_format)
        sys.exit(EXIT_SUCCESS)
    if args.merge:
        _run_merge(config, args.output_format)
        sys.exit(EXIT_SUCCESS)
    if args.generate_data:
        _run_generate_data(config, args.output_format)
        sys.exit(EXIT_SUCCESS)
    if args.compliance_export:
        _run_compliance_export(config, args.compliance_export, args.output_format)
        sys.exit(EXIT_SUCCESS)


def _report_training_error(
    json_output: bool, payload: dict, log_msg: str, exit_code: int, *, with_traceback: bool = False
) -> None:
    """Emit a training-pipeline error and exit with *exit_code*.

    Centralizes the "JSON to stdout vs human log message" split. Pass
    ``with_traceback=True`` for unexpected exceptions where the stack trace
    is more useful than a one-line message.
    """
    if json_output:
        print(json.dumps(payload))
    elif with_traceback:
        logger.exception(log_msg)
    else:
        logger.error(log_msg)
    sys.exit(exit_code)


def _run_training_pipeline(config, args, json_output: bool) -> None:
    """Run the full training pipeline (model load → data → trainer.train → cleanup)."""
    try:
        # Defer heavy imports so `--help`, `--version`, and `--dry-run` stay lightweight.
        from .data import prepare_dataset
        from .model import get_model_and_tokenizer
        from .trainer import ForgeTrainer
        from .utils import manage_checkpoints, setup_authentication

        if not config.model.offline:
            setup_authentication(config.auth.hf_token if config.auth else None)
        else:
            logger.info("Skipping HF authentication (offline mode).")

        model, tokenizer = get_model_and_tokenizer(config)
        dataset = prepare_dataset(config, tokenizer)

        resume_checkpoint = None
        if args.resume:
            resume_checkpoint = _resolve_resume_checkpoint(config.training.output_dir, args.resume)

        trainer = ForgeTrainer(model=model, tokenizer=tokenizer, config=config, dataset=dataset)
        result = trainer.train(resume_from_checkpoint=resume_checkpoint)

        logger.info("Cleaning up intermediate checkpoints...")
        manage_checkpoints(config.training.output_dir, action="keep")

        _output_result(result, args.output_format)
        if result.success and config.evaluation and getattr(config.evaluation, "require_human_approval", False):
            sys.exit(EXIT_AWAITING_APPROVAL)
        sys.exit(EXIT_SUCCESS if result.success else EXIT_EVAL_FAILURE)

    except ImportError as e:
        _report_training_error(
            json_output,
            payload={"success": False, "error": f"Missing dependency: {e}"},
            log_msg=f"Missing dependency: {e}. Check your installation.",
            exit_code=EXIT_TRAINING_ERROR,
        )
    except Exception as e:
        _report_training_error(
            json_output,
            payload={"success": False, "error": str(e)},
            log_msg="Training pipeline failed.",
            exit_code=EXIT_TRAINING_ERROR,
            with_traceback=True,
        )


def main():
    args = parse_args()

    # Phase 10 subcommand dispatch — no --config required.
    command = getattr(args, "command", None)
    if command is not None:
        json_output = getattr(args, "output_format", "text") == "json"
        log_level = "WARNING" if getattr(args, "quiet", False) else getattr(args, "log_level", "INFO")
        _setup_logging(log_level, json_format=json_output)
        _dispatch_subcommand(command, args)

    _maybe_run_wizard(args)

    if not args.config:
        print("Error: --config is required. Use --help for usage.", file=sys.stderr)
        sys.exit(EXIT_CONFIG_ERROR)

    json_output = args.output_format == "json"
    log_level = "WARNING" if args.quiet else args.log_level
    _setup_logging(log_level, json_format=json_output)

    config = _load_config_or_exit(args.config, json_output)
    _apply_offline_flag(config, args.offline)
    _maybe_run_no_train_mode(config, args)
    _run_training_pipeline(config, args, json_output)


if __name__ == "__main__":
    main()
