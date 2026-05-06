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

_PUBLIC_EXIT_CODES = frozenset(
    {EXIT_SUCCESS, EXIT_CONFIG_ERROR, EXIT_TRAINING_ERROR, EXIT_EVAL_FAILURE, EXIT_AWAITING_APPROVAL}
)
