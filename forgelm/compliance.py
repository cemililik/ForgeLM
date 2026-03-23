"""EU AI Act compliance and training data provenance tracking.

Generates machine-readable audit trails, training manifests, and
compliance reports for regulated industries.
"""
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("forgelm.compliance")


def compute_dataset_fingerprint(dataset_path: str) -> Dict[str, Any]:
    """Compute a fingerprint for a dataset file or directory.

    Returns a dict with hash, size, and metadata for provenance tracking.
    """
    fingerprint = {
        "path": dataset_path,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if os.path.isfile(dataset_path):
        stat = os.stat(dataset_path)
        fingerprint["size_bytes"] = stat.st_size
        fingerprint["modified"] = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()

        # Compute SHA-256 hash
        sha256 = hashlib.sha256()
        with open(dataset_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        fingerprint["sha256"] = sha256.hexdigest()
    else:
        # HF Hub dataset — record the identifier
        fingerprint["source"] = "huggingface_hub"
        fingerprint["dataset_id"] = dataset_path

    return fingerprint


def generate_training_manifest(
    config: Any,
    metrics: Dict[str, float],
    resource_usage: Optional[Dict[str, Any]] = None,
    safety_result: Optional[Dict[str, Any]] = None,
    judge_result: Optional[Dict[str, Any]] = None,
    benchmark_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate a comprehensive training manifest for audit purposes.

    This is the primary compliance artifact — a structured record of
    everything about the training run.
    """
    manifest = {
        "forgelm_version": _get_version(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_lineage": {
            "base_model": config.model.name_or_path,
            "backend": config.model.backend,
            "adapter_method": _describe_adapter_method(config),
            "quantization": "4-bit NF4" if config.model.load_in_4bit else "none",
            "trust_remote_code": config.model.trust_remote_code,
        },
        "training_parameters": {
            "trainer_type": config.training.trainer_type,
            "epochs": config.training.num_train_epochs,
            "batch_size": config.training.per_device_train_batch_size,
            "gradient_accumulation_steps": config.training.gradient_accumulation_steps,
            "learning_rate": config.training.learning_rate,
            "max_length": config.model.max_length,
            "lora_r": config.lora.r,
            "lora_alpha": config.lora.alpha,
            "lora_dropout": config.lora.dropout,
            "dora": config.lora.use_dora,
            "target_modules": config.lora.target_modules,
        },
        "data_provenance": {
            "primary_dataset": config.data.dataset_name_or_path,
            "fingerprint": compute_dataset_fingerprint(config.data.dataset_name_or_path),
            "shuffle": config.data.shuffle,
            "clean_text": config.data.clean_text,
        },
        "evaluation_results": {
            "metrics": metrics,
        },
    }

    # Add extra datasets provenance
    extra_datasets = getattr(config.data, "extra_datasets", None)
    if extra_datasets:
        manifest["data_provenance"]["extra_datasets"] = [
            {"path": p, "fingerprint": compute_dataset_fingerprint(p)}
            for p in extra_datasets
        ]

    # Add resource usage
    if resource_usage:
        manifest["resource_usage"] = resource_usage

    # Add safety results
    if safety_result:
        manifest["evaluation_results"]["safety"] = safety_result

    # Add judge results
    if judge_result:
        manifest["evaluation_results"]["llm_judge"] = judge_result

    # Add benchmark results
    if benchmark_result:
        manifest["evaluation_results"]["benchmark"] = benchmark_result

    return manifest


def export_compliance_artifacts(
    manifest: Dict[str, Any],
    config: Any,
    output_dir: str,
) -> List[str]:
    """Export all compliance artifacts to a directory.

    Generates:
    - compliance_report.json: Full structured audit trail
    - training_manifest.yaml: Human-readable training summary
    - data_provenance.json: Dataset fingerprints and lineage

    Returns list of generated file paths.
    """
    import yaml

    os.makedirs(output_dir, exist_ok=True)
    generated_files = []

    # 1. Full compliance report (JSON)
    report_path = os.path.join(output_dir, "compliance_report.json")
    with open(report_path, "w") as f:
        json.dump(manifest, f, indent=2, default=str)
    generated_files.append(report_path)
    logger.info("Compliance report saved to %s", report_path)

    # 2. Training manifest (YAML — human-readable)
    manifest_path = os.path.join(output_dir, "training_manifest.yaml")
    yaml_manifest = {
        "forgelm_version": manifest["forgelm_version"],
        "generated_at": manifest["generated_at"],
        "base_model": manifest["model_lineage"]["base_model"],
        "adapter_method": manifest["model_lineage"]["adapter_method"],
        "trainer_type": manifest["training_parameters"]["trainer_type"],
        "dataset": manifest["data_provenance"]["primary_dataset"],
        "epochs": manifest["training_parameters"]["epochs"],
        "final_metrics": {
            k: round(v, 4) if isinstance(v, float) else v
            for k, v in manifest["evaluation_results"]["metrics"].items()
            if not k.startswith("benchmark/")
        },
    }
    with open(manifest_path, "w") as f:
        yaml.dump(yaml_manifest, f, default_flow_style=False, sort_keys=False)
    generated_files.append(manifest_path)
    logger.info("Training manifest saved to %s", manifest_path)

    # 3. Data provenance (JSON)
    provenance_path = os.path.join(output_dir, "data_provenance.json")
    with open(provenance_path, "w") as f:
        json.dump(manifest["data_provenance"], f, indent=2, default=str)
    generated_files.append(provenance_path)
    logger.info("Data provenance saved to %s", provenance_path)

    return generated_files


def _describe_adapter_method(config: Any) -> str:
    """Generate a human-readable description of the adapter method."""
    parts = []
    if config.model.load_in_4bit:
        parts.append("QLoRA (4-bit NF4)")
    else:
        parts.append("LoRA")
    if config.lora.use_dora:
        parts.append("DoRA")
    parts.append(f"r={config.lora.r}")
    return " + ".join(parts)


def _get_version() -> str:
    try:
        from forgelm import __version__
        return __version__
    except ImportError:
        return "unknown"
