"""
GGUF export for post-training model distribution.

Wraps llama-cpp-python's ``convert_hf_to_gguf.py`` conversion script to
produce quantised GGUF files that can be served by Ollama, llama.cpp, and
compatible runtimes.

Optional dependency: ``pip install forgelm[export]``

Usage (programmatic):
    from forgelm.export import export_model
    result = export_model("./outputs/final_model", "./model.gguf", quant="q4_k_m")

Usage (CLI):
    forgelm export ./outputs/final_model --format gguf --quant q4_k_m --output model.gguf
"""
from __future__ import annotations

import hashlib
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger("forgelm.export")

SUPPORTED_FORMATS = frozenset({"gguf"})
SUPPORTED_QUANTS = frozenset({"q2_k", "q3_k_m", "q4_k_m", "q5_k_m", "q8_0", "f16"})

# llama.cpp quantisation type strings used by convert_hf_to_gguf.py
_OUTTYPE_MAP = {
    "f16": "f16",
    "q2_k": "q2_k",
    "q3_k_m": "q3_k_m",
    "q4_k_m": "q4_k_m",
    "q5_k_m": "q5_k_m",
    "q8_0": "q8_0",
}


@dataclass
class ExportResult:
    """Result of an ``export_model`` call."""

    success: bool
    output_path: Optional[str] = None
    format: str = "gguf"
    quant: Optional[str] = None
    sha256: Optional[str] = None
    size_bytes: Optional[int] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# Converter discovery
# ---------------------------------------------------------------------------


def _find_converter_script() -> str:
    """Locate llama-cpp-python's HF → GGUF conversion script.

    Raises:
        ImportError: When llama-cpp-python is not installed.
        FileNotFoundError: When the conversion script cannot be found inside
            the package.  Upgrade to llama-cpp-python >= 0.2.90.
    """
    try:
        import llama_cpp  # noqa: F401
    except ImportError as e:
        raise ImportError(
            "llama-cpp-python is required for GGUF export.  "
            "Install the export extra: pip install 'forgelm[export]'"
        ) from e

    import llama_cpp

    pkg_root = os.path.dirname(os.path.abspath(llama_cpp.__file__))

    candidates = [
        os.path.join(pkg_root, "convert_hf_to_gguf.py"),
        os.path.join(pkg_root, "scripts", "convert_hf_to_gguf.py"),
        # Some versions place it one level up
        os.path.join(os.path.dirname(pkg_root), "convert_hf_to_gguf.py"),
    ]

    for path in candidates:
        if os.path.isfile(path):
            logger.debug("Found converter at %s", path)
            return path

    raise FileNotFoundError(
        "convert_hf_to_gguf.py not found inside the llama-cpp-python installation.  "
        "Upgrade to llama-cpp-python >= 0.2.90: pip install 'llama-cpp-python>=0.2.90'"
    )


# ---------------------------------------------------------------------------
# Adapter merge helper
# ---------------------------------------------------------------------------


def _merge_adapter(model_path: str, adapter_path: str, merged_dir: str) -> None:
    """Merge a PEFT LoRA adapter into the base model and save to *merged_dir*.

    The merged weights are in fp16 HuggingFace format, ready for GGUF conversion.
    """
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    logger.info("Merging adapter %s into base model %s ...", adapter_path, model_path)
    tokenizer = AutoTokenizer.from_pretrained(model_path)
    model = AutoModelForCausalLM.from_pretrained(model_path, torch_dtype="auto", device_map="cpu")
    model = PeftModel.from_pretrained(model, adapter_path)
    model = model.merge_and_unload()

    os.makedirs(merged_dir, exist_ok=True)
    model.save_pretrained(merged_dir, safe_serialization=True)
    tokenizer.save_pretrained(merged_dir)
    logger.info("Merged model saved to %s", merged_dir)


# ---------------------------------------------------------------------------
# SHA-256 helper
# ---------------------------------------------------------------------------


def _sha256_file(path: str) -> str:
    """Compute the SHA-256 digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Compliance integration
# ---------------------------------------------------------------------------


def _update_integrity_manifest(model_dir: str, export_result: ExportResult) -> None:
    """Append the exported artifact to model_integrity.json if it exists."""
    import json

    integrity_path = os.path.join(model_dir, "model_integrity.json")
    if not os.path.isfile(integrity_path):
        return

    try:
        with open(integrity_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        artifact = {
            "file": os.path.basename(export_result.output_path or ""),
            "format": export_result.format,
            "quant": export_result.quant,
            "sha256": export_result.sha256,
            "size_bytes": export_result.size_bytes,
        }
        data.setdefault("exported_artifacts", []).append(artifact)

        with open(integrity_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        logger.info("model_integrity.json updated with exported artifact.")
    except Exception as e:
        logger.debug("Could not update model_integrity.json: %s", e)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def export_model(
    model_path: str,
    output_path: str,
    *,
    format: str = "gguf",
    quant: str = "q4_k_m",
    adapter: Optional[str] = None,
    update_integrity: bool = True,
    extra_args: Optional[List[str]] = None,
) -> ExportResult:
    """Export a HuggingFace model to GGUF format.

    If *adapter* is provided the adapter is first merged into the base model
    (saved to a temporary ``_merged`` sibling directory) before conversion.

    Args:
        model_path: Path to a saved HuggingFace model directory.
        output_path: Destination ``.gguf`` file path.
        format: Export format.  Only ``"gguf"`` is currently supported.
        quant: Quantisation type.  One of
            ``q2_k, q3_k_m, q4_k_m, q5_k_m, q8_0, f16``.
        adapter: Optional PEFT adapter directory to merge before export.
        update_integrity: When ``True``, appends the exported artifact's
            SHA-256 to ``model_integrity.json`` in the model directory.
        extra_args: Additional CLI arguments forwarded to the converter script.

    Returns:
        :class:`ExportResult` with SHA-256, file size, and output path.
    """
    format = format.lower()
    quant = quant.lower()

    if format not in SUPPORTED_FORMATS:
        return ExportResult(
            success=False,
            format=format,
            error=f"Unsupported format '{format}'. Supported: {', '.join(sorted(SUPPORTED_FORMATS))}",
        )

    if quant not in SUPPORTED_QUANTS:
        return ExportResult(
            success=False,
            quant=quant,
            error=(
                f"Unsupported quantisation '{quant}'. "
                f"Supported: {', '.join(sorted(SUPPORTED_QUANTS))}"
            ),
        )

    try:
        converter = _find_converter_script()
    except (ImportError, FileNotFoundError) as e:
        return ExportResult(success=False, format=format, quant=quant, error=str(e))

    # Merge adapter if requested
    source_path = model_path
    merged_dir: Optional[str] = None
    if adapter:
        merged_dir = model_path.rstrip("/\\") + "_merged_for_export"
        try:
            _merge_adapter(model_path, adapter, merged_dir)
            source_path = merged_dir
        except Exception as e:
            return ExportResult(
                success=False,
                format=format,
                quant=quant,
                error=f"Adapter merge failed: {e}",
            )

    # Build converter command
    outtype = _OUTTYPE_MAP[quant]
    cmd: List[str] = [
        sys.executable,
        converter,
        source_path,
        "--outfile",
        output_path,
        "--outtype",
        outtype,
    ]
    if extra_args:
        cmd.extend(extra_args)

    logger.info("Running GGUF conversion: %s", " ".join(cmd))

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            error_detail = proc.stderr.strip() or proc.stdout.strip() or "unknown error"
            logger.error("GGUF conversion failed (exit %d): %s", proc.returncode, error_detail)
            return ExportResult(
                success=False,
                format=format,
                quant=quant,
                error=f"Converter exited with code {proc.returncode}: {error_detail[:500]}",
            )
    except Exception as e:
        return ExportResult(success=False, format=format, quant=quant, error=str(e))

    if not os.path.isfile(output_path):
        return ExportResult(
            success=False,
            format=format,
            quant=quant,
            error=f"Conversion appeared to succeed but output file not found: {output_path}",
        )

    # Compute artifact stats
    digest = _sha256_file(output_path)
    size_bytes = os.path.getsize(output_path)

    result = ExportResult(
        success=True,
        output_path=output_path,
        format=format,
        quant=quant,
        sha256=digest,
        size_bytes=size_bytes,
    )

    logger.info(
        "GGUF export complete: %s (%.1f GB, quant=%s, sha256=%s…)",
        output_path,
        size_bytes / (1024 ** 3),
        quant,
        digest[:12],
    )

    if update_integrity:
        _update_integrity_manifest(model_path, result)

    return result
