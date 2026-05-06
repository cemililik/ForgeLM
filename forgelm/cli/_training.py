"""Training-mode pipeline (model → data → trainer.train → cleanup)."""

from __future__ import annotations

import json
import sys

from ._exit_codes import EXIT_AWAITING_APPROVAL, EXIT_EVAL_FAILURE, EXIT_SUCCESS, EXIT_TRAINING_ERROR
from ._logging import logger
from ._result import _output_result
from ._resume import _resolve_resume_checkpoint


def _report_training_error(
    json_output: bool, payload: dict, log_msg: str, exit_code: int, *, with_traceback: bool = False
) -> None:
    """Emit a training-pipeline error and exit with *exit_code*.

    Centralizes the "JSON to stdout vs human log message" split. Pass
    ``with_traceback=True`` for unexpected exceptions where the stack trace
    is more useful than a one-line message.
    """
    if with_traceback:
        logger.exception(log_msg)
    else:
        logger.error(log_msg)
    if json_output:
        print(json.dumps(payload))
    sys.exit(exit_code)


def _run_training_pipeline(config, args, json_output: bool) -> None:
    """Run the full training pipeline (model load → data → trainer.train → cleanup)."""
    # Defer heavy imports so `--help`, `--version`, and `--dry-run` stay lightweight.
    # ImportError here means a required optional extra is missing — surface as install hint.
    try:
        from ..data import prepare_dataset
        from ..model import get_model_and_tokenizer
        from ..trainer import ForgeTrainer
        from ..utils import manage_checkpoints, setup_authentication
    except ImportError as e:
        _report_training_error(
            json_output,
            payload={"success": False, "error": f"Missing dependency: {e}"},
            log_msg=f"Missing dependency: {e}. Check your installation.",
            exit_code=EXIT_TRAINING_ERROR,
        )

    try:
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

        logger.info("Preserving intermediate checkpoints (action=keep).")
        manage_checkpoints(config.training.output_dir, action="keep")

        _output_result(result, args.output_format)
        if result.success and config.evaluation and getattr(config.evaluation, "require_human_approval", False):
            sys.exit(EXIT_AWAITING_APPROVAL)
        sys.exit(EXIT_SUCCESS if result.success else EXIT_EVAL_FAILURE)

    except Exception as e:  # noqa: BLE001 — best-effort: top-of-CLI training catch.  ForgeTrainer.train() crosses every concern (HF model load, dataset load, TRL trainer, safety eval, judge eval, audit emission, compliance export, webhook notify); any leak from the inner narrow-class catches must surface as a structured CLI failure (with traceback in the log) rather than a Python traceback dumped to stdout that breaks JSON parsers.  # NOSONAR
        _report_training_error(
            json_output,
            payload={"success": False, "error": str(e)},
            log_msg="Training pipeline failed.",
            exit_code=EXIT_TRAINING_ERROR,
            with_traceback=True,
        )
