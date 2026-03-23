import os
import logging
import shutil
import time
import tarfile
import uuid
from huggingface_hub import login

logger = logging.getLogger("forgelm.utils")

# HF token paths in priority order (modern XDG path first, then legacy)
_HF_TOKEN_PATHS = [
    os.path.expanduser("~/.cache/huggingface/token"),
    os.path.expanduser("~/.huggingface/token"),
]

def setup_authentication(token: str = None) -> None:
    """Configures Hugging Face authentication."""
    hf_token = token or os.getenv("HUGGINGFACE_TOKEN")

    if not hf_token:
        # Fallback to local token store if nothing provided
        for token_path in _HF_TOKEN_PATHS:
            try:
                with open(token_path, 'r') as f:
                    hf_token = f.read().strip()
                if hf_token:
                    break
            except FileNotFoundError:
                continue

        if not hf_token:
            logger.warning("No Hugging Face token found. Some models/datasets might not load.")
            return

    logger.info("Authenticating with Hugging Face...")
    login(token=hf_token)

def manage_checkpoints(checkpoint_dir: str, action: str = "keep") -> None:
    """Handles logic for deleting or compressing checkpoints post-training.

    Actions:
        keep: No-op (default safety behavior — checkpoints remain as-is)
        delete: Remove entire checkpoint directory
        compress: Create tar.gz archive and keep originals
    """
    if not os.path.exists(checkpoint_dir):
        return

    if action == "keep":
        logger.debug("Keeping checkpoints in %s (no cleanup).", checkpoint_dir)
    elif action == "delete":
        shutil.rmtree(checkpoint_dir, ignore_errors=True)
        logger.info("Checkpoints in %s deleted.", checkpoint_dir)
    elif action == "compress":
        # Use UUID suffix to prevent archive name collisions
        archive_name = f"checkpoints_{int(time.time())}_{uuid.uuid4().hex[:6]}.tar.gz"
        logger.info("Compressing checkpoints to %s...", archive_name)
        with tarfile.open(archive_name, "w:gz") as tar:
            tar.add(checkpoint_dir, arcname=os.path.basename(checkpoint_dir))
        logger.info("Compression complete.")
    else:
        logger.warning("Unknown checkpoint action: '%s'. Keeping checkpoints.", action)
