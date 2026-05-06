"""Optional ``--wizard`` flow that drops a generated config into ``args.config``."""

from __future__ import annotations

import sys

from ._exit_codes import EXIT_SUCCESS


def _maybe_run_wizard(args) -> None:
    """Open the interactive wizard when --wizard was passed; mutates *args*."""
    if not args.wizard:
        return
    from ..wizard import run_wizard

    config_path = run_wizard()
    if config_path:
        args.config = config_path
    else:
        sys.exit(EXIT_SUCCESS)
