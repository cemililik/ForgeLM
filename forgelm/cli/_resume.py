"""Resume-checkpoint resolution helper for ``--resume``."""

from __future__ import annotations

import os
import sys
from typing import Optional

from ._exit_codes import EXIT_CONFIG_ERROR
from ._logging import logger


def _resolve_resume_checkpoint(checkpoint_dir: str, resume_arg: str) -> Optional[str]:
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

    try:
        entries = os.listdir(checkpoint_dir)
    except OSError as exc:
        logger.error("Cannot list checkpoint directory %s: %s", checkpoint_dir, exc)
        sys.exit(EXIT_CONFIG_ERROR)

    checkpoint_dirs = sorted(
        [d for d in entries if d.startswith("checkpoint-") and os.path.isdir(os.path.join(checkpoint_dir, d))],
        key=lambda x: int(x.split("-")[-1]) if x.split("-")[-1].isdigit() else 0,
    )

    if not checkpoint_dirs:
        logger.warning("No checkpoint-* directories found in %s. Starting fresh.", checkpoint_dir)
        return None

    latest = os.path.join(checkpoint_dir, checkpoint_dirs[-1])
    logger.info("Auto-detected checkpoint for resume: %s", latest)
    return latest
