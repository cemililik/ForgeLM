"""``forgelm quickstart`` dispatcher (template → config → train → chat)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .._exit_codes import _PUBLIC_EXIT_CODES, EXIT_CONFIG_ERROR, EXIT_SUCCESS, EXIT_TRAINING_ERROR
from .._logging import _CLI_MODULE, logger


def _build_quickstart_inherited_flags(args) -> tuple[list[str], list[str]]:
    """Return (train_flags, chat_flags) propagated from parent argv.

    Both lists carry --quiet / --log-level / --offline. Neither list
    carries --output-format json: the quickstart parent owns the JSON
    envelope, and forwarding it to the training subprocess produces two
    top-level JSON objects on stdout (subprocess result + parent envelope)
    making the stream unparseable by any JSON consumer.
    """
    train_flags: list[str] = []
    chat_flags: list[str] = []
    if getattr(args, "quiet", False):
        train_flags.append("--quiet")
        chat_flags.append("--quiet")
    log_level = getattr(args, "log_level", None)
    if log_level:
        train_flags += ["--log-level", log_level]
        chat_flags += ["--log-level", log_level]
    if getattr(args, "offline", False):
        train_flags.append("--offline")
        chat_flags.append("--offline")
    return train_flags, chat_flags


def _emit_quickstart_list(output_format: str) -> None:
    """Print the registered quickstart templates and exit (text or JSON)."""
    from ...quickstart import format_template_list, list_templates

    if output_format == "json":
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
            for t in list_templates()
        ]
        print(json.dumps(payload, indent=2))
    else:
        print(format_template_list())


def _emit_quickstart_result(result, output_format: str) -> None:
    """Print the quickstart-generation summary (JSON envelope or text)."""
    from ...quickstart import summarize_result

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


def _load_quickstart_train_paths(config_path: Path) -> tuple[str, str]:
    """Read the generated YAML and return ``(output_dir, final_model_dir)``.

    Kept tiny + standalone so quickstart never has to import the heavy config
    validation pipeline just to find the trained checkpoint directory.
    """
    import yaml

    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    training = cfg.get("training", {}) or {}
    return (
        training.get("output_dir", "./checkpoints"),
        training.get("final_model_dir", "final_model"),
    )


def _run_quickstart_train_subprocess(args, config_path: Path) -> None:
    """Spawn `forgelm --config <generated>` as a child process; exit on non-zero.

    The child's raw return code is logged for debuggability but is mapped to
    one of ForgeLM's documented exit codes (0/1/2/3/4) before propagating —
    signal-derived codes like 137 (SIGKILL) or 139 (SIGSEGV) shouldn't leak
    out of the public CLI contract.
    """
    import subprocess  # nosec B404 — argv-list usage only

    inherited, _ = _build_quickstart_inherited_flags(args)
    train_cmd = [sys.executable, "-m", _CLI_MODULE, *inherited, "--config", os.path.abspath(config_path)]
    logger.info("Starting training: %s", " ".join(train_cmd))
    # Security justification (Codacy / Bandit B603 / ruff S603):
    # - argv is a fixed list, not a shell string — shell=False is implicit.
    # - argv[0] is sys.executable (the running Python), not a user-controlled
    #   command name. argv[1] is "-m" with the literal _CLI_MODULE constant.
    # - The only user-influenced segment is `os.path.abspath(config_path)`,
    #   which is passed verbatim as a single argv element (no shell expansion,
    #   no string concatenation).
    # → No command-injection or shell-metachar surface. Safe to ignore.
    try:
        train_rc = subprocess.run(train_cmd, check=False).returncode  # noqa: S603  # nosec B603
    except OSError as exc:
        logger.error("Failed to launch training subprocess: %s", exc)
        sys.exit(EXIT_TRAINING_ERROR)
    if train_rc != 0:
        logger.error("Training exited with code %d", train_rc)
        exit_code = train_rc if train_rc in _PUBLIC_EXIT_CODES else EXIT_TRAINING_ERROR
        sys.exit(exit_code)


def _run_quickstart_chat_subprocess(args, config_path: Path) -> None:
    """Auto-launch `forgelm chat <trained-model>` after a successful training run."""
    import subprocess  # nosec B404 — argv-list usage only

    # Re-import via the package facade so monkeypatched
    # ``forgelm.cli._load_quickstart_train_paths`` references resolve.
    from forgelm import cli as _cli_facade

    output_dir, final_subdir = _cli_facade._load_quickstart_train_paths(config_path)
    final_model_dir = Path(output_dir) / final_subdir
    if not final_model_dir.is_dir():
        logger.warning(
            "Skipping auto-chat: trained model directory not found at %s. Run `forgelm chat <model_path>` manually.",
            final_model_dir,
        )
        return

    _, inherited_chat = _build_quickstart_inherited_flags(args)
    chat_cmd = [sys.executable, "-m", _CLI_MODULE, *inherited_chat, "chat", os.path.abspath(final_model_dir)]
    logger.info("Launching chat REPL: %s", " ".join(chat_cmd))
    # Same security justification as the training subprocess above:
    # argv list-form, sys.executable head, _CLI_MODULE literal, only the
    # final_model_dir is dynamic and passed as a single argv element. No
    # shell, no concatenation → no injection surface.
    chat_rc = subprocess.run(chat_cmd, check=False).returncode  # noqa: S603  # nosec B603
    # 130 == SIGINT (Ctrl-C is the normal way to leave the REPL). Anything else
    # non-zero is a crash worth surfacing, but chat exit is not the operator's
    # training-success signal so we still exit 0 — the training run already
    # succeeded by the time we got here.
    if chat_rc not in (0, 130):
        logger.warning("Chat subprocess exited with code %d", chat_rc)


def _run_quickstart_train_then_chat(args, result) -> None:
    """Run training then (unless --no-chat) auto-launch the chat REPL.

    Extracted from ``_run_quickstart_cmd`` so the dispatcher stays a flat
    sequence of steps. ``_run_quickstart_train_subprocess`` exits on
    non-zero training rc; if it returns we know training succeeded, so the
    chat branch is reachable without an explicit success check.
    """
    # Spec: invoke training automatically. Use a subprocess so each phase keeps
    # its own clean process state and Ctrl-C is honoured cleanly.
    _run_quickstart_train_subprocess(args, result.config_path)

    if args.no_chat:
        sys.exit(EXIT_SUCCESS)

    _run_quickstart_chat_subprocess(args, result.config_path)
    sys.exit(EXIT_SUCCESS)


def _run_quickstart_cmd(args, output_format: str) -> None:
    """Dispatch the ``forgelm quickstart`` subcommand.

    Three flows: ``--list`` (print templates and exit); plain
    ``forgelm quickstart TEMPLATE`` (generate config + auto-train + auto-chat);
    ``--dry-run`` (generate config, print next step, do not train).
    """
    from ...quickstart import run_quickstart

    if args.list:
        _emit_quickstart_list(output_format)
        sys.exit(EXIT_SUCCESS)

    if not args.template:
        err = "forgelm quickstart: TEMPLATE is required (or pass --list to see the menu)."
        if output_format == "json":
            print(json.dumps({"success": False, "error": err}))
        else:
            logger.error(err)
        sys.exit(EXIT_CONFIG_ERROR)

    try:
        result = run_quickstart(
            args.template,
            model_override=args.model,
            dataset_override=args.dataset,
            output_path=args.output,
            dry_run=args.dry_run,
        )
    except (FileNotFoundError, FileExistsError, ValueError) as e:
        # FileExistsError is raised by _resolve_dataset when an explicit
        # --output dir already contains a seed dataset (refuses to clobber);
        # treat it as a config-level error so the user gets the actionable
        # message instead of a Python traceback.
        if output_format == "json":
            print(json.dumps({"success": False, "error": str(e)}))
        else:
            logger.error("Quickstart failed: %s", e)
        sys.exit(EXIT_CONFIG_ERROR)

    _emit_quickstart_result(result, output_format)

    if result.dry_run:
        sys.exit(EXIT_SUCCESS)

    _run_quickstart_train_then_chat(args, result)
