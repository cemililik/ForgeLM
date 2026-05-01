"""Public re-exports for the ``forgelm`` CLI package.

This facade preserves the pre-Faz-15 ``forgelm.cli`` import surface — the
tests, the ``forgelm`` console script, and the
``python -m forgelm.cli`` entry point all keep resolving against this
module.

Every name re-exported here is part of the load-bearing contract:

- Public exit codes consumed by CI/CD pipelines.
- ``parse_args`` / ``main`` as the entry-point pair.
- The handful of underscore-prefixed helpers that tests reach via
  ``from forgelm.cli import _name`` or ``patch("forgelm.cli._name", ...)``
  — the dotted path must resolve *here* for monkeypatch to work.

The package layout matches the cohesion ceiling in
:doc:`docs/standards/architecture` — each sub-module owns one concern,
with this facade keeping the historical import surface intact.
"""

from __future__ import annotations

# argparse type validators + shared subparser flags.
from ._argparse_types import (
    _add_common_subparser_flags,  # noqa: F401 — re-export for tests
    _non_negative_float,  # noqa: F401 — re-export for tests
    _non_negative_int,  # noqa: F401 — re-export for tests
)

# Config loading + offline flag application (training mode).
from ._config_load import (
    _apply_offline_flag,  # noqa: F401 — re-export for tests
    _load_config_or_exit,  # noqa: F401 — re-export for tests
)

# Top-level dispatcher + main() entry point.
from ._dispatch import (
    _dispatch_subcommand,  # noqa: F401 — re-export for tests
    main,
)

# Dry-run mode helpers.
from ._dry_run import (
    _build_dry_run_result,  # noqa: F401 — re-export for tests
    _compliance_dry_run_fields,  # noqa: F401 — re-export for tests
    _evaluation_dry_run_fields,  # noqa: F401 — re-export for tests
    _galore_dry_run_fields,  # noqa: F401 — re-export for tests
    _run_dry_run,
)

# Public exit codes consumed by CI/CD pipelines.
from ._exit_codes import (
    _PUBLIC_EXIT_CODES,  # noqa: F401 — re-export for tests
    EXIT_AWAITING_APPROVAL,
    EXIT_CONFIG_ERROR,
    EXIT_EVAL_FAILURE,
    EXIT_SUCCESS,
    EXIT_TRAINING_ERROR,
)

# Fit-check (VRAM estimate) mode.
from ._fit_check import _run_fit_check

# Version + logging helpers.
from ._logging import (
    _CLI_MODULE,  # noqa: F401 — re-export for tests / quickstart subprocess
    _get_version,
    _setup_logging,
    logger,  # noqa: F401 — re-export for tests
)

# Non-training modes (benchmark-only, merge, generate-data, compliance-export).
from ._no_train_modes import (
    _maybe_run_no_train_mode,  # noqa: F401 — re-export for tests
    _run_benchmark_only,  # noqa: F401 — re-export for tests
    _run_compliance_export,
    _run_generate_data,  # noqa: F401 — re-export for tests
    _run_merge,  # noqa: F401 — re-export for tests
)

# Parser (registrars + parse_args).
from ._parser import (
    _add_approve_subcommand,  # noqa: F401 — re-export for tests
    _add_audit_subcommand,  # noqa: F401 — re-export for tests
    _add_chat_subcommand,  # noqa: F401 — re-export for tests
    _add_deploy_subcommand,  # noqa: F401 — re-export for tests
    _add_export_subcommand,  # noqa: F401 — re-export for tests
    _add_ingest_subcommand,  # noqa: F401 — re-export for tests
    _add_quickstart_subcommand,  # noqa: F401 — re-export for tests
    _add_reject_subcommand,  # noqa: F401 — re-export for tests
    _add_verify_audit_subcommand,  # noqa: F401 — re-export for tests
    parse_args,
)

# Result formatting helpers.
from ._result import (
    _build_result_json_envelope,  # noqa: F401 — re-export for tests
    _log_benchmark_summary,  # noqa: F401 — re-export for tests
    _log_cost_summary,  # noqa: F401 — re-export for tests
    _log_result_status,  # noqa: F401 — re-export for tests
    _output_result,
)

# Resume checkpoint resolution.
from ._resume import _resolve_resume_checkpoint

# Training pipeline.
from ._training import (
    _report_training_error,  # noqa: F401 — re-export for tests
    _run_training_pipeline,  # noqa: F401 — re-export for tests
)

# Wizard mode.
from ._wizard import _maybe_run_wizard  # noqa: F401 — re-export for tests

# Approve / reject subcommands (Article 14 human-approval gate).
from .subcommands._approve import (
    _atomic_rename_or_move,  # noqa: F401 — re-export for tests
    _build_approval_notifier,  # noqa: F401 — re-export for tests
    _find_human_approval_decision_event,  # noqa: F401 — re-export for tests
    _find_human_approval_required_event,  # noqa: F401 — re-export for tests
    _load_metrics_from_manifest,  # noqa: F401 — re-export for tests
    _resolve_approver_identity,  # noqa: F401 — re-export for tests
    _run_approve_cmd,  # noqa: F401 — re-export for tests
    _run_reject_cmd,  # noqa: F401 — re-export for tests
)

# Audit subcommand (+ legacy --data-audit worker).
from .subcommands._audit import (
    _run_audit_cmd,  # noqa: F401 — re-export for tests
    _run_data_audit,
)

# Chat / export / deploy / ingest subcommand dispatchers.
from .subcommands._chat import _run_chat_cmd  # noqa: F401 — re-export for tests
from .subcommands._deploy import _run_deploy_cmd  # noqa: F401 — re-export for tests
from .subcommands._export import _run_export_cmd  # noqa: F401 — re-export for tests
from .subcommands._ingest import _run_ingest_cmd  # noqa: F401 — re-export for tests

# Quickstart subcommand (multi-step orchestrator).
from .subcommands._quickstart import (
    _build_quickstart_inherited_flags,
    _emit_quickstart_list,  # noqa: F401 — re-export for tests
    _emit_quickstart_result,  # noqa: F401 — re-export for tests
    _load_quickstart_train_paths,  # noqa: F401 — re-export for tests
    _run_quickstart_chat_subprocess,  # noqa: F401 — re-export for tests
    _run_quickstart_cmd,  # noqa: F401 — re-export for tests
    _run_quickstart_train_subprocess,  # noqa: F401 — re-export for tests
    _run_quickstart_train_then_chat,  # noqa: F401 — re-export for tests
)

# Verify-audit subcommand.
from .subcommands._verify_audit import _run_verify_audit_cmd  # noqa: F401 — re-export for tests

__all__ = [
    # Public exit codes
    "EXIT_SUCCESS",
    "EXIT_CONFIG_ERROR",
    "EXIT_TRAINING_ERROR",
    "EXIT_EVAL_FAILURE",
    "EXIT_AWAITING_APPROVAL",
    # Public entry points
    "parse_args",
    "main",
    # Test-touched helpers (kept stable per split-design §2)
    "_get_version",
    "_setup_logging",
    "_resolve_resume_checkpoint",
    "_run_dry_run",
    "_run_fit_check",
    "_run_compliance_export",
    "_run_data_audit",
    "_output_result",
    "_build_quickstart_inherited_flags",
    "_maybe_run_wizard",
]
