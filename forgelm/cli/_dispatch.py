"""Top-level dispatcher + ``main()`` entry point.

Subcommand dispatchers are looked up via the package facade
(:mod:`forgelm.cli`) at call time so test monkeypatches against
``forgelm.cli._run_*_cmd`` resolve correctly.
"""

from __future__ import annotations

import json
import sys
import warnings

from ._config_load import _apply_offline_flag, _load_config_or_exit
from ._exit_codes import EXIT_CONFIG_ERROR, EXIT_SUCCESS, EXIT_TRAINING_ERROR
from ._logging import _setup_logging, logger
from ._no_train_modes import _maybe_run_no_train_mode
from ._parser import parse_args
from ._training import _run_training_pipeline
from ._wizard import _maybe_run_wizard


def _dispatch_subcommand(command: str, args) -> None:
    """Run a Phase 10 / 10.5 / 11 / 11.5 subcommand and exit.

    Subcommands handled here: ``chat``, ``export``, ``deploy``, ``quickstart``,
    ``ingest``, ``audit``, ``verify-audit``, ``approve``, ``reject``. Each
    terminates the process via ``sys.exit`` after its own dispatcher returns —
    the trainer/training code path never runs when a subcommand is in play.

    Dispatchers are looked up via the package facade so tests that
    ``patch("forgelm.cli._run_*_cmd", ...)`` see their mock invoked.
    """
    # Late import via the package facade so monkeypatched
    # ``forgelm.cli._run_*_cmd`` references resolve correctly.
    from forgelm import cli as _cli_facade

    if command == "chat":
        # _run_chat_cmd's REPL catches KeyboardInterrupt internally for the
        # input prompt; this outer guard covers Ctrl-C during model load /
        # welcome banner render, before the REPL loop has started.
        try:
            _cli_facade._run_chat_cmd(args)
        except KeyboardInterrupt:
            sys.exit(EXIT_TRAINING_ERROR)
        sys.exit(EXIT_SUCCESS)
    elif command == "export":
        _cli_facade._run_export_cmd(args, getattr(args, "output_format", "text"))
        sys.exit(EXIT_SUCCESS)
    elif command == "deploy":
        _cli_facade._run_deploy_cmd(args, getattr(args, "output_format", "text"))
        sys.exit(EXIT_SUCCESS)
    elif command == "quickstart":
        try:
            _cli_facade._run_quickstart_cmd(args, getattr(args, "output_format", "text"))
        except KeyboardInterrupt:
            sys.exit(EXIT_TRAINING_ERROR)
        sys.exit(EXIT_SUCCESS)
    elif command == "ingest":
        _cli_facade._run_ingest_cmd(args, getattr(args, "output_format", "text"))
        sys.exit(EXIT_SUCCESS)
    elif command == "audit":
        _cli_facade._run_audit_cmd(args, getattr(args, "output_format", "text"))
        sys.exit(EXIT_SUCCESS)
    elif command == "verify-audit":
        sys.exit(_cli_facade._run_verify_audit_cmd(args))
    elif command == "approve":
        _cli_facade._run_approve_cmd(args, getattr(args, "output_format", "text"))
        sys.exit(EXIT_SUCCESS)
    elif command == "reject":
        _cli_facade._run_reject_cmd(args, getattr(args, "output_format", "text"))
        sys.exit(EXIT_SUCCESS)
    else:
        logger.error("Unrecognized subcommand: %r. This is a bug — please report it.", command)
        sys.exit(EXIT_TRAINING_ERROR)


def main():
    args = parse_args()

    # Phase 10 subcommand dispatch — no --config required.
    command = getattr(args, "command", None)
    if command is not None:
        json_output = getattr(args, "output_format", "text") == "json"
        log_level = "WARNING" if getattr(args, "quiet", False) else getattr(args, "log_level", "INFO")
        _setup_logging(log_level, json_format=json_output)
        _dispatch_subcommand(command, args)

    # --data-audit operates on a JSONL file/directory only — no config needed.
    # Run before the config-required check so operators can audit raw data
    # without writing a YAML. Phase 11.5 promoted the same code path to
    # `forgelm audit PATH` (a real subcommand); the legacy flag is preserved
    # as an alias and slated for removal in v0.7.0 — Phase 13 wires up the
    # deprecation signalling at this dispatch site.
    if getattr(args, "data_audit", None):
        json_output = args.output_format == "json"
        log_level = "WARNING" if args.quiet else args.log_level
        _setup_logging(log_level, json_format=json_output)
        # Phase 13 (Faz 13): emit a structured Python ``DeprecationWarning``
        # so `pytest -W error::DeprecationWarning` and `python -Wd` tooling
        # surface it, plus an append-only audit-log event so operators who
        # only read the JSONL trail see the migration signal too. Cadence
        # for the v0.7.0 removal follows the "Deprecation cadence" section
        # in ``docs/standards/release.md`` (one-minor warning window
        # minimum).
        warnings.warn(
            "`forgelm --data-audit PATH` is deprecated and will be removed "
            "in v0.7.0. Use the `forgelm audit PATH` subcommand instead — "
            "same behaviour, same output. "
            "See docs/standards/release.md#deprecation-cadence for the removal timeline.",
            DeprecationWarning,
            stacklevel=2,
        )
        # Audit-log event: append-only Article 12 record of the legacy
        # invocation so compliance reviewers can prove the operator was
        # warned. The logger writes to ``<target>/audit_log.jsonl`` next to
        # the report this run is about to produce. Resolve the target the
        # same way ``_run_data_audit`` does (default ``./audit``) so the
        # event lands in the same directory as the report.
        legacy_target = args.output or "./audit"
        try:
            from ..compliance import AuditLogger

            AuditLogger(legacy_target).log_event(
                "cli.legacy_flag_invoked",
                flag="--data-audit",
                replacement="forgelm audit",
                version="v0.7.0 removal",
            )
        except OSError as audit_exc:
            # Non-fatal: the audit log is a best-effort telemetry record
            # for the deprecation notice. The DeprecationWarning has
            # already fired; the audit run itself must still proceed —
            # losing the legacy-flag breadcrumb is preferable to aborting
            # a working pipeline because the output dir is read-only.
            logger.debug("Failed to record legacy-flag audit event: %s", audit_exc)
        # Late import via the package facade so monkeypatched
        # ``forgelm.cli._run_data_audit`` references resolve correctly.
        from forgelm import cli as _cli_facade

        _cli_facade._run_data_audit(
            args.data_audit,
            args.output,
            args.output_format,
        )
        sys.exit(EXIT_SUCCESS)

    _maybe_run_wizard(args)

    if not args.config:
        if getattr(args, "output_format", "text") == "json":
            print(json.dumps({"success": False, "error": "--config is required."}))
        else:
            print("Error: --config is required. Use --help for usage.", file=sys.stderr)
        sys.exit(EXIT_CONFIG_ERROR)

    json_output = args.output_format == "json"
    log_level = "WARNING" if args.quiet else args.log_level
    _setup_logging(log_level, json_format=json_output)

    config = _load_config_or_exit(args.config, json_output)
    _apply_offline_flag(config, args.offline)
    _maybe_run_no_train_mode(config, args)
    _run_training_pipeline(config, args, json_output)
