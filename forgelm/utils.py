import os
import shutil
import time
import tarfile
from huggingface_hub import login

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
            print("Warning: No Hugging Face token found. Some models/datasets might not load.")
            return

    print("Authenticating with Hugging Face...")
    login(token=hf_token)

def manage_checkpoints(checkpoint_dir: str, action: str = "keep") -> None:
    """Handles logic for deleting or compressing checkpoints post-training."""
    if not os.path.exists(checkpoint_dir):
        return
        
    if action == "delete":
        shutil.rmtree(checkpoint_dir, ignore_errors=True)
        print(f"Checkpoints in {checkpoint_dir} deleted.")
    elif action == "compress":
        archive_name = f"checkpoints_{int(time.time())}.tar.gz"
        print(f"Compressing checkpoints to {archive_name}...")
        with tarfile.open(archive_name, "w:gz") as tar:
            tar.add(checkpoint_dir, arcname=os.path.basename(checkpoint_dir))
        print("Compression complete.")
