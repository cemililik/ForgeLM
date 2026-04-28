"""EU AI Act compliance, training data provenance, and audit trail generation.

Covers: Article 9 (Risk Management), Article 10 (Data Governance),
Article 11 + Annex IV (Technical Documentation), Article 12 (Record-Keeping),
Article 13 (Transparency/Deployer Instructions), Article 14 (Human Oversight),
Article 15 (Model Integrity).
"""

import concurrent.futures
import hashlib
import json
import logging
import os
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("forgelm.compliance")


# ---------------------------------------------------------------------------
# Art. 12: Structured Audit Event Log
# ---------------------------------------------------------------------------


class AuditLogger:
    """Append-only JSON Lines audit log for EU AI Act Art. 12 record-keeping."""

    def __init__(self, output_dir: str, run_id: Optional[str] = None):
        self.run_id = run_id or f"fg-{uuid.uuid4().hex[:12]}"
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.log_path = os.path.join(output_dir, "audit_log.jsonl")
        self.operator = os.getenv("FORGELM_OPERATOR", os.getenv("USER", "unknown"))
        self._prev_hash = self._load_last_hash()

    def _load_last_hash(self) -> str:
        """Read the last line hash from an existing log file to restore chain continuity.

        Distinguishes "no file" (legitimate first run, returns ``"genesis"``)
        from "file exists but unreadable" (filesystem error or corrupt log,
        raises ``OSError``). The previous version swallowed any exception
        with ``logger.debug`` and silently re-rooted the chain — invisible
        at default INFO log level, undetectable downstream.
        """
        if not os.path.isfile(self.log_path):
            return "genesis"
        try:
            with open(self.log_path, "rb") as f:
                f.seek(0, 2)
                size = f.tell()
                if size == 0:
                    return "genesis"
                f.seek(max(0, size - 4096))
                tail = f.read()
        except OSError as e:
            # Real I/O failure — surface loudly. A silent re-root would
            # break the Article 12 record-keeping contract: a downstream
            # verifier cannot tell a missing chain head from a corrupt one.
            raise OSError(
                f"Audit log exists at {self.log_path!r} but could not be read: {e}. "
                "Refusing to silently re-root the hash chain."
            ) from e
        try:
            lines = [ln for ln in tail.decode("utf-8").splitlines() if ln.strip()]
        except UnicodeDecodeError as e:
            raise ValueError(
                f"Audit log {self.log_path!r} contains non-UTF-8 data — likely corrupt: {e}. "
                "Refusing to silently re-root the hash chain."
            ) from e
        if lines:
            last_line = lines[-1].encode("utf-8")
            return hashlib.sha256(last_line).hexdigest()
        return "genesis"

    def log_event(self, event: str, **details) -> None:
        """Append a tamper-evident structured event to the audit log.

        Each entry includes the SHA-256 hash of the previous entry,
        creating a hash chain that detects modifications or deletions.

        Hash advancement is **post-write**: ``self._prev_hash`` is only
        updated after the line has been successfully appended. The previous
        version advanced the hash before the write and swallowed the write
        failure with ``logger.warning`` — leaving an in-memory chain that
        looked valid but a log file with a missing entry.
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "operator": self.operator,
            "event": event,
            "prev_hash": self._prev_hash,
            **details,
        }
        entry_json = json.dumps(entry, default=str)
        try:
            with open(self.log_path, "a") as f:
                f.write(entry_json + "\n")
        except OSError as e:
            # Article 12 record-keeping is a load-bearing artefact; a write
            # failure must surface to the caller, not be quietly swallowed.
            raise OSError(
                f"Failed to write audit event {event!r} to {self.log_path!r}: {e}. "
                "The hash chain has NOT been advanced — retry or fail the run."
            ) from e
        # Only advance the chain after the write succeeded.
        self._prev_hash = hashlib.sha256(entry_json.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Art. 10: Data Governance & Quality Report
# ---------------------------------------------------------------------------


def _build_text_length_stats(split_data: Any, split_name: str) -> Optional[Dict[str, Any]]:
    """Compute min/max/mean/median/p95 of the ``text`` column, if present."""
    if not (hasattr(split_data, "column_names") and "text" in split_data.column_names):
        return None
    try:
        texts = split_data["text"]
        lengths = sorted(len(t) for t in texts if isinstance(t, str))
    except Exception as exc:
        logger.debug("Could not compute text stats for %s: %s", split_name, exc)
        return None
    if not lengths:
        return None
    return {
        "min": lengths[0],
        "max": lengths[-1],
        "mean": round(sum(lengths) / len(lengths), 1),
        "median": lengths[len(lengths) // 2],
        "p95": lengths[int(len(lengths) * 0.95)],
    }


def _build_split_info(split_name: str, split_data: Any) -> Dict[str, Any]:
    """Per-split sample count + column schema + length distribution."""
    info: Dict[str, Any] = {"sample_count": len(split_data)}
    if hasattr(split_data, "column_names"):
        info["columns"] = split_data.column_names
    text_length = _build_text_length_stats(split_data, split_name)
    if text_length:
        info["text_length"] = text_length
    return info


def _governance_section(config: Any) -> Optional[Dict[str, Any]]:
    """Return the operator-supplied Article 10 metadata block, if any."""
    gov_cfg = getattr(config.data, "governance", None)
    if not gov_cfg:
        return None
    return {
        "collection_method": gov_cfg.collection_method,
        "annotation_process": gov_cfg.annotation_process,
        "known_biases": gov_cfg.known_biases,
        "personal_data_included": gov_cfg.personal_data_included,
        "dpia_completed": gov_cfg.dpia_completed,
    }


def _maybe_inline_audit_report(config: Any) -> Optional[Dict[str, Any]]:
    """Read ``data_audit_report.json`` from ``training.output_dir`` if it's there.

    Loud-but-non-fatal hint when the file is missing: the audit CLI
    defaults to ``./audit/`` whereas the trainer's output_dir is
    typically ``./checkpoints/`` — without explicit alignment the
    inlining silently no-ops and the governance bundle ships without
    the Article 10 data-quality section.
    """
    output_dir = getattr(getattr(config, "training", None), "output_dir", None)
    if not output_dir:
        return None
    audit_path = os.path.join(output_dir, "data_audit_report.json")
    if not os.path.isfile(audit_path):
        logger.info(
            "No data_audit_report.json at %s — governance report will lack the "
            "Article 10 data-quality section. Run "
            "`forgelm audit <dataset> --output %s` before training to populate it.",
            audit_path,
            output_dir,
        )
        return None
    try:
        with open(audit_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        # Audit JSON is best-effort enrichment — corrupt UTF-8 or a
        # malformed file must not abort governance report generation.
        logger.warning("Could not inline data_audit_report.json (%s): %s", audit_path, exc)
        return None


def generate_data_governance_report(config: Any, dataset: Dict[str, Any]) -> Dict[str, Any]:
    """Generate data quality and governance report per EU AI Act Article 10.

    When an audit report (``data_audit_report.json``) was produced by
    ``forgelm --data-audit`` and lives in the trainer's checkpoint dir,
    its findings are inlined under the ``data_audit`` key so the governance
    artifact is a single self-contained document rather than a pointer.
    """
    report: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "primary_dataset": config.data.dataset_name_or_path,
        "splits": {name: _build_split_info(name, data) for name, data in dataset.items()},
    }

    governance = _governance_section(config)
    if governance:
        report["governance"] = governance

    audit = _maybe_inline_audit_report(config)
    if audit is not None:
        report["data_audit"] = audit

    return report


# ---------------------------------------------------------------------------
# Art. 15: Model Integrity Verification
# ---------------------------------------------------------------------------


def _hash_file(filepath: str, rel_path: str) -> dict:
    sha256 = hashlib.sha256()
    size = 0
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
            size += len(chunk)
    return {"file": rel_path, "sha256": sha256.hexdigest(), "size_bytes": size}


def generate_model_integrity(final_path: str) -> Dict[str, Any]:
    """Compute SHA-256 checksums of all output model artifacts."""
    integrity = {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "model_path": final_path,
        "artifacts": [],
    }

    if not os.path.isdir(final_path):
        return integrity

    file_pairs = []
    for root, _dirs, files in os.walk(final_path):
        for filename in sorted(files):
            filepath = os.path.join(root, filename)
            rel_path = os.path.relpath(filepath, final_path)
            file_pairs.append((filepath, rel_path))

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futures = [ex.submit(_hash_file, fp, rp) for fp, rp in file_pairs]
        integrity["artifacts"] = [f.result() for f in concurrent.futures.as_completed(futures)]

    integrity["artifacts"].sort(key=lambda x: x["file"])

    return integrity


# ---------------------------------------------------------------------------
# Data Provenance (existing, unchanged)
# ---------------------------------------------------------------------------


def compute_dataset_fingerprint(dataset_path: str) -> Dict[str, Any]:
    """Compute a fingerprint for a dataset file or directory.

    The previous version was decorated with ``@lru_cache(maxsize=32)`` keyed
    only on the path string. Three problems compounded:

    1. **TOCTOU**: a long-running process that audits the same path twice
       (training restart, multi-stage pipeline) would return the *first*
       fingerprint even after the file had been rewritten — silently
       producing stale Article 10 evidence.
    2. **No symlink resolution**: ``./data.jsonl`` and a symlink to it
       hashed independently; mutating the target invalidated only one
       cache entry.
    3. **Non-atomic stat + read**: ``os.stat()`` and the subsequent open
       read could race a concurrent writer, producing a (size, mtime,
       sha256) triple where the size belonged to one revision and the
       hash to another.

    The cache is dropped (cost is dominated by the file read anyway, and
    a per-process memo would still suffer the staleness problem); symlinks
    are resolved before hashing; ``stat`` is captured from the same open
    file descriptor as the SHA-256 stream so the triple is consistent.
    """
    fingerprint = {
        "path": dataset_path,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if os.path.isfile(dataset_path):
        # Resolve symlinks: the artefact we attest to is the resolved file,
        # not the link. Preserve the original path so the caller can still
        # see what they passed.
        resolved = os.path.realpath(dataset_path)
        if resolved != dataset_path:
            fingerprint["resolved_path"] = resolved

        sha256 = hashlib.sha256()
        with open(resolved, "rb") as f:
            # Capture stat from the open fd so size/mtime cannot drift from
            # the byte stream we are hashing — a concurrent writer would
            # surface as an inconsistent fingerprint downstream rather than
            # a silent partial read.
            stat = os.fstat(f.fileno())
            fingerprint["size_bytes"] = stat.st_size
            fingerprint["modified"] = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        fingerprint["sha256"] = sha256.hexdigest()
    else:
        fingerprint["source"] = "huggingface_hub"
        fingerprint["dataset_id"] = dataset_path
        # Attempt to capture dataset version/revision from HF Hub
        try:
            from datasets import load_dataset_builder

            builder = load_dataset_builder(dataset_path)
            if builder.info.version:
                fingerprint["version"] = str(builder.info.version)
            if builder.info.description:
                fingerprint["description"] = builder.info.description[:200]
            if builder.info.download_size:
                fingerprint["download_size_bytes"] = builder.info.download_size
        except Exception as e:
            logger.debug("HF Hub metadata fetch skipped for '%s': %s", dataset_path, e)

    return fingerprint


# ---------------------------------------------------------------------------
# Art. 11 + Annex IV: Training Manifest & Technical Documentation
# ---------------------------------------------------------------------------


def generate_training_manifest(
    config: Any,
    metrics: Dict[str, float],
    resource_usage: Optional[Dict[str, Any]] = None,
    safety_result: Optional[Dict[str, Any]] = None,
    judge_result: Optional[Dict[str, Any]] = None,
    benchmark_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate a comprehensive training manifest for audit purposes."""
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

    # Annex IV provider metadata
    comp_cfg = getattr(config, "compliance", None)
    if comp_cfg:
        manifest["annex_iv"] = {
            "provider_name": comp_cfg.provider_name,
            "provider_contact": comp_cfg.provider_contact,
            "system_name": comp_cfg.system_name,
            "intended_purpose": comp_cfg.intended_purpose,
            "known_limitations": comp_cfg.known_limitations,
            "system_version": comp_cfg.system_version,
            "risk_classification": comp_cfg.risk_classification,
        }

    # Risk assessment
    risk_cfg = getattr(config, "risk_assessment", None)
    if risk_cfg:
        manifest["risk_assessment"] = {
            "intended_use": risk_cfg.intended_use,
            "foreseeable_misuse": risk_cfg.foreseeable_misuse,
            "risk_category": risk_cfg.risk_category,
            "mitigation_measures": risk_cfg.mitigation_measures,
            "vulnerable_groups_considered": risk_cfg.vulnerable_groups_considered,
        }

    # Extra datasets provenance
    extra_datasets = getattr(config.data, "extra_datasets", None)
    if extra_datasets:
        manifest["data_provenance"]["extra_datasets"] = [
            {"path": p, "fingerprint": compute_dataset_fingerprint(p)} for p in extra_datasets
        ]

    # Monitoring config
    mon_cfg = getattr(config, "monitoring", None)
    if mon_cfg and mon_cfg.enabled:
        manifest["monitoring"] = {
            "endpoint": mon_cfg.endpoint or f"${mon_cfg.endpoint_env}",
            "metrics_export": mon_cfg.metrics_export,
            "alert_on_drift": mon_cfg.alert_on_drift,
            "check_interval_hours": mon_cfg.check_interval_hours,
        }

    if resource_usage:
        manifest["resource_usage"] = resource_usage
    if safety_result:
        manifest["evaluation_results"]["safety"] = safety_result
    if judge_result:
        manifest["evaluation_results"]["llm_judge"] = judge_result
    if benchmark_result:
        manifest["evaluation_results"]["benchmark"] = benchmark_result

    return manifest


# ---------------------------------------------------------------------------
# Art. 13: Deployer Instructions
# ---------------------------------------------------------------------------


def _sanitize_md(text: Optional[str]) -> str:
    """Escape user-controlled text before embedding in Markdown to prevent injection.

    Accepts ``None`` (treated as "Not specified") so callers can pass through
    optional config fields without a per-site None-check.
    """
    if not text:
        return "Not specified"
    text = text.replace("\n", " ").replace("\r", " ")
    text = text.replace("|", "\\|")
    return text.strip()


def generate_deployer_instructions(config: Any, metrics: Dict[str, float], final_path: str) -> str:
    """Generate deployer instructions document per EU AI Act Article 13."""
    comp_cfg = getattr(config, "compliance", None)
    risk_cfg = getattr(config, "risk_assessment", None)

    provider = _sanitize_md(comp_cfg.provider_name if comp_cfg else "")
    purpose = _sanitize_md(comp_cfg.intended_purpose if comp_cfg else "")
    limitations = _sanitize_md(comp_cfg.known_limitations if comp_cfg else "")
    system_name = comp_cfg.system_name if comp_cfg else config.model.name_or_path.split("/")[-1]

    content = f"""# Deployer Instructions — {system_name}

> Auto-generated by ForgeLM v{_get_version()} per EU AI Act Article 13.
> This document is intended for personnel deploying this model in production.

## 1. System Identity

| Field | Value |
|-------|-------|
| System Name | {system_name} |
| Provider | {provider} |
| Base Model | {config.model.name_or_path} |
| Fine-Tuning Method | {_describe_adapter_method(config)} |
| Model Location | {final_path} |

## 2. Intended Purpose

{purpose}

## 3. Known Limitations

{limitations}

**This model should NOT be used for:**
"""
    if risk_cfg and risk_cfg.foreseeable_misuse:
        for misuse in risk_cfg.foreseeable_misuse:
            content += f"- {misuse}\n"
    else:
        content += "- Use cases not covered by the intended purpose above\n"

    content += """
## 4. Performance Metrics

| Metric | Value |
|--------|-------|
"""
    for k, v in sorted(metrics.items()):
        if isinstance(v, float):
            content += f"| {k} | {v:.4f} |\n"

    content += """
## 5. Human Oversight Requirements

- A qualified human operator must review model outputs before they are used in consequential decisions.
- The operator must be able to override or discard model outputs.
- Incident reporting: contact the provider if the model produces harmful, incorrect, or unexpected outputs.

## 6. Hardware Requirements

- The model requires a GPU with sufficient VRAM for inference.
- Minimum: NVIDIA GPU with 8GB+ VRAM (for quantized inference).
- Recommended: NVIDIA A100/H100 for production workloads.

## 7. Incident Reporting

If the model produces harmful, biased, or incorrect outputs in production:
1. Document the input that caused the issue
2. Stop using the model for that use case
3. Report to the provider immediately
"""

    doc_path = os.path.join(final_path, "deployer_instructions.md")
    os.makedirs(final_path, exist_ok=True)
    with open(doc_path, "w") as f:
        f.write(content)
    logger.info("Deployer instructions saved to %s", doc_path)
    return doc_path


# ---------------------------------------------------------------------------
# Export: All Compliance Artifacts
# ---------------------------------------------------------------------------


def export_compliance_artifacts(
    manifest: Dict[str, Any],
    output_dir: str,
) -> List[str]:
    """Export all compliance artifacts to a directory.

    The *manifest* (produced by :func:`generate_training_manifest`) already
    contains all the config-derived data needed for the artifacts, so the
    config object itself is not required here.
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

    # 2. Training manifest (YAML)
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

    # 3. Data provenance (JSON)
    provenance_path = os.path.join(output_dir, "data_provenance.json")
    with open(provenance_path, "w") as f:
        json.dump(manifest["data_provenance"], f, indent=2, default=str)
    generated_files.append(provenance_path)

    # 4. Risk assessment (JSON) — if present
    if "risk_assessment" in manifest:
        risk_path = os.path.join(output_dir, "risk_assessment.json")
        with open(risk_path, "w") as f:
            json.dump(manifest["risk_assessment"], f, indent=2)
        generated_files.append(risk_path)

    # 5. Annex IV metadata (JSON) — if present
    if "annex_iv" in manifest:
        annex_path = os.path.join(output_dir, "annex_iv_metadata.json")
        with open(annex_path, "w") as f:
            json.dump(manifest["annex_iv"], f, indent=2)
        generated_files.append(annex_path)

    logger.info("Compliance artifacts exported to %s (%d files)", output_dir, len(generated_files))
    return generated_files


# ---------------------------------------------------------------------------
# Evidence Bundle (ZIP)
# ---------------------------------------------------------------------------


def export_evidence_bundle(output_dir: str, bundle_path: str) -> str:
    """Package all compliance artifacts into a single auditor-ready ZIP archive."""
    if not os.path.isdir(output_dir):
        logger.warning("Compliance directory not found: %s", output_dir)
        return ""

    with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(output_dir):
            for filename in files:
                filepath = os.path.join(root, filename)
                arcname = os.path.relpath(filepath, os.path.dirname(output_dir))
                zf.write(filepath, arcname)

    logger.info("Evidence bundle saved to %s", bundle_path)
    return bundle_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _describe_adapter_method(config: Any) -> str:
    parts = []
    method = getattr(config.lora, "method", "lora")
    if config.model.load_in_4bit:
        parts.append("QLoRA (4-bit NF4)")
    elif method == "pissa":
        parts.append("PiSSA")
    elif method == "rslora":
        parts.append("rsLoRA")
    else:
        parts.append("LoRA")
    if config.lora.use_dora or method == "dora":
        parts.append("DoRA")
    if getattr(config.training, "galore_enabled", False):
        parts.append(f"GaLore ({config.training.galore_optim})")
    parts.append(f"r={config.lora.r}")
    return " + ".join(parts)


def _get_version() -> str:
    """Resolve ForgeLM's version for compliance-manifest stamping.

    Prefers the installed distribution metadata (single source of truth with
    ``pyproject.toml``); falls back to the package-level ``__version__``
    attribute (which itself uses ``importlib.metadata``); finally returns
    ``"unknown"`` if both paths fail (raw source import without install).
    """
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _pkg_version

    try:
        return _pkg_version("forgelm")
    except PackageNotFoundError:
        try:
            from forgelm import __version__

            return __version__
        except ImportError:  # pragma: no cover
            return "unknown"
