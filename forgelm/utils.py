import os
import logging
import shutil
import time
import tarfile
from huggingface_hub import login

logger = logging.getLogger("forgelm.utils")

def setup_authentication(token: str = None) -> None:
    """Configures Hugging Face authentication."""
    hf_token = token or os.getenv("HUGGINGFACE_TOKEN")

    if not hf_token:
        # Fallback to local token store if nothing provided
        token_path = os.path.expanduser("~/.huggingface/token")
        try:
            with open(token_path, 'r') as f:
                hf_token = f.read().strip()
        except FileNotFoundError:
            logger.warning("No Hugging Face token found. Some models/datasets might not load.")
            return

    logger.info("Authenticating with Hugging Face...")
    login(token=hf_token)

def manage_checkpoints(checkpoint_dir: str, action: str = "keep") -> None:
    """Handles logic for deleting or compressing checkpoints post-training."""
    if not os.path.exists(checkpoint_dir):
        return

    if action == "delete":
        shutil.rmtree(checkpoint_dir, ignore_errors=True)
        logger.info("Checkpoints in %s deleted.", checkpoint_dir)
    elif action == "compress":
        archive_name = f"checkpoints_{int(time.time())}.tar.gz"
        logger.info("Compressing checkpoints to %s...", archive_name)
        with tarfile.open(archive_name, "w:gz") as tar:
            tar.add(checkpoint_dir, arcname=os.path.basename(checkpoint_dir))
        logger.info("Compression complete.")
