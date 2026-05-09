"""Optional ``--wizard`` flow that drops a generated config into ``args.config``."""

from __future__ import annotations

import sys

from ._exit_codes import EXIT_SUCCESS, EXIT_WIZARD_CANCELLED


def _maybe_run_wizard(args) -> None:
    """Open the interactive wizard when --wizard was passed; mutates *args*.

    Exit-code semantics (D2):
        - ``EXIT_SUCCESS`` (0) + caller continues into training: the
          operator generated a config AND answered "yes" to "start now".
        - ``EXIT_SUCCESS`` (0) immediately: the operator generated a
          config but answered "no" — the YAML deliverable was produced,
          training simply happens later via ``forgelm --config <path>``.
        - ``EXIT_WIZARD_CANCELLED`` (5): the operator never wrote a
          config (Ctrl-C, non-tty refusal, cancel).  Distinct from
          ``EXIT_SUCCESS`` so CI can differentiate "wizard finished" vs
          "wizard never produced output".
    """
    if not args.wizard:
        # PR-D-B3 (PR-E review fix): warn the operator who passed
        # --wizard-start-from without --wizard so the typo doesn't
        # silently no-op into the regular config-driven path.
        if getattr(args, "wizard_start_from", None):
            print(
                "  ⚠ --wizard-start-from has no effect without --wizard.  "
                "Add --wizard to launch the interactive wizard preloaded from your YAML."
            )
        return
    from ..wizard import run_wizard_full

    # ``--wizard-start-from`` (E3 / PR-D) preloads the wizard with an
    # existing YAML so the operator can iterate on a prior config
    # without losing answers.  ``getattr`` for back-compat: callers
    # constructing argparse Namespaces by hand might not include the
    # field on legacy code paths.
    start_from = getattr(args, "wizard_start_from", None)
    outcome = run_wizard_full(start_from=start_from)
    if outcome.cancelled:
        sys.exit(EXIT_WIZARD_CANCELLED)
    # YAML was produced — either start training now or exit cleanly so
    # the operator can launch later.
    if outcome.start_training:
        args.config = outcome.config_path
        return
    sys.exit(EXIT_SUCCESS)


__all__ = ["_maybe_run_wizard", "EXIT_SUCCESS", "EXIT_WIZARD_CANCELLED"]
