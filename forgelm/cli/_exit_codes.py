"""ForgeLM CLI exit-code contract.

These integer codes are part of the public CLI surface — CI/CD pipelines
branch on them. Any other value (e.g. signal-derived 128+N codes) is
clamped to :data:`EXIT_TRAINING_ERROR` before propagating.
"""

from __future__ import annotations

EXIT_SUCCESS = 0
EXIT_CONFIG_ERROR = 1
EXIT_TRAINING_ERROR = 2
EXIT_EVAL_FAILURE = 3
EXIT_AWAITING_APPROVAL = 4
# 5: operator cancelled the wizard before producing a config (e.g.
# Ctrl-C, declined to save, non-tty stdin refusal).  Distinct from
# ``EXIT_SUCCESS`` so CI can tell "wizard finished with a config" apart
# from "wizard never saved anything".  Picked 5 (the next free integer
# in the public 0-4 contract) rather than 130 (signal-derived) because
# clean cancels through `cancel`/`q` aren't signal-driven.
EXIT_WIZARD_CANCELLED = 5

_PUBLIC_EXIT_CODES = frozenset(
    {
        EXIT_SUCCESS,
        EXIT_CONFIG_ERROR,
        EXIT_TRAINING_ERROR,
        EXIT_EVAL_FAILURE,
        EXIT_AWAITING_APPROVAL,
        EXIT_WIZARD_CANCELLED,
    }
)
