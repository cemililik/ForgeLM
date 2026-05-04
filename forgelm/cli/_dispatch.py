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


def _output_format_for(args) -> str:
    """Pull the ``--output-format`` value off ``args`` with the standard default."""
    return getattr(args, "output_format", "text")


def _dispatch_subcommand(command: str, args) -> None:
    """Run a Phase 10 / 10.5 / 11 / 11.5 / Wave 2a subcommand and exit.

    Subcommands handled here: ``chat``, ``export``, ``deploy``,
    ``quickstart``, ``ingest``, ``audit``, ``doctor``, ``verify-audit``,
    ``approve``, ``reject``, ``approvals``.  Each terminates the process
    via ``sys.exit`` after its own dispatcher returns — the trainer code
    path never runs when a subcommand is in play.

    Dispatchers are looked up via the package facade so tests that
    ``patch("forgelm.cli._run_*_cmd", ...)`` see their mock invoked.
    The dispatch table replaced an if/elif chain in Wave 2a Round-2 to
    drop SonarCloud S3776 cognitive complexity (was 16, ceiling 15) and
    to keep the registry literal — adding a new subcommand is now a
    single-row edit.
    """
    # Late import via the package facade so monkeypatched
    # ``forgelm.cli._run_*_cmd`` references resolve correctly.
    from forgelm import cli as _cli_facade

    # ``verify-audit`` is the one subcommand whose dispatcher returns an
    # exit code instead of calling sys.exit itself, so it is special-cased
    # below the table rather than wedging an extra branch into every entry.
    if command == "verify-audit":
        sys.exit(_cli_facade._run_verify_audit_cmd(args))

    # name -> dispatcher attribute on the package facade.  Resolved lazily
    # so test-time monkeypatches against ``forgelm.cli._run_*_cmd`` are
    # honoured.
    table = {
        "chat": "_run_chat_cmd",
        "export": "_run_export_cmd",
        "deploy": "_run_deploy_cmd",
        "quickstart": "_run_quickstart_cmd",
        "ingest": "_run_ingest_cmd",
        "audit": "_run_audit_cmd",
        "doctor": "_run_doctor_cmd",
        "approve": "_run_approve_cmd",
        "reject": "_run_reject_cmd",
        "approvals": "_run_approvals_cmd",
    }
    dispatcher_name = table.get(command)
    if dispatcher_name is None:
        logger.error("Unrecognized subcommand: %r. This is a bug — please report it.", command)
        sys.exit(EXIT_TRAINING_ERROR)
    dispatcher = getattr(_cli_facade, dispatcher_name)

    # Two call shapes: ``chat`` only takes ``args`` (its REPL handles
    # output formatting itself); everything else takes ``(args, output_format)``.
    output_format = _output_format_for(args)
    try:
        if command == "chat":
            dispatcher(args)
        else:
            dispatcher(args, output_format)
    except KeyboardInterrupt:
        # All SIGINTs route through the public exit-code contract
        # (EXIT_TRAINING_ERROR = 2, "runtime-error class").  ``raise`` would
        # have let Python convert SIGINT into the shell-shaped 128+SIGINT
        # = 130 code, which is outside the documented 0/1/2/3/4 surface
        # and would surprise CI/CD scripts that branch on exit code.
        # Wave 2a Round-3 review (CodeRabbit): every SIGINT path lands on a
        # public code regardless of subcommand.
        sys.exit(EXIT_TRAINING_ERROR)
    sys.exit(EXIT_SUCCESS)


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
