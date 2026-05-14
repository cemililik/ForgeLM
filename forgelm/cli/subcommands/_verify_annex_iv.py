"""``forgelm verify-annex-iv`` — EU AI Act Annex IV artifact verification.

Phase 36 closure of GH-004.  Mirrors the verify-audit pattern (Phase 6):
takes a path to a compliance artifact JSON file, validates the field
completeness against the EU AI Act Annex IV §1-9 requirement set, and
recomputes the manifest hash to detect tampering.

The library function lives in :mod:`forgelm.compliance` so integrators
can call it from their own pipelines without going through the CLI;
this module is the dispatcher + JSON-envelope wrapper.

Exit codes (per ``docs/standards/error-handling.md``):

- 0 — every required field present + manifest hash matches.
- 1 — required field missing OR manifest hash mismatch (operator-
  actionable; the artifact is not Annex IV compliant as-is).
- 2 — runtime error (file not found, unreadable, malformed JSON).
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, NoReturn, Tuple

from .._exit_codes import EXIT_CONFIG_ERROR, EXIT_SUCCESS, EXIT_TRAINING_ERROR
from .._logging import logger

# EU AI Act Annex IV §1-9 — the nine required categories every
# high-risk-system technical-documentation file must carry.  We map
# each category to the JSON keys we expect at the top level of the
# artifact (a small subset matches `compliance.py`'s emit shape).
#
# NOTE: this is a *minimum* set; richer artefacts may add more keys.
# The check fails when a required key is missing OR when its value is
# the empty string / empty dict / empty list (operator likely forgot
# to populate it from the auto-generation template).
_ANNEX_IV_REQUIRED_FIELDS: Tuple[Tuple[str, str], ...] = (
    ("system_identification", "Annex IV §1 — system identification (name, version, provider, intended_purpose)"),
    ("intended_purpose", "Annex IV §1 — intended purpose statement"),
    ("system_components", "Annex IV §2 — software / hardware components + supplier list"),
    ("computational_resources", "Annex IV §2(g) — compute resources used during training"),
    ("data_governance", "Annex IV §2(d) — data sources, governance, validation methodology"),
    ("technical_documentation", "Annex IV §3-5 — design + development methodology"),
    ("monitoring_and_logging", "Annex IV §6 — post-market monitoring + audit-log presence"),
    ("performance_metrics", "Annex IV §7 — accuracy / robustness / cybersecurity metrics"),
    ("risk_management", "Annex IV §9 — risk management system reference (Art. 9 alignment)"),
)


class VerifyAnnexIVResult:
    """Structured result of an Annex IV artifact verification.

    Mirrors ``forgelm.compliance.VerifyResult`` (used by verify-audit)
    so integrators get a uniform shape across the verification toolbelt.
    """

    __slots__ = ("valid", "reason", "missing_fields", "manifest_hash_actual", "manifest_hash_expected")

    def __init__(
        self,
        *,
        valid: bool,
        reason: str = "",
        missing_fields: List[str] | None = None,
        manifest_hash_actual: str = "",
        manifest_hash_expected: str = "",
    ) -> None:
        self.valid = valid
        self.reason = reason
        self.missing_fields = list(missing_fields or [])
        self.manifest_hash_actual = manifest_hash_actual
        self.manifest_hash_expected = manifest_hash_expected

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "reason": self.reason,
            "missing_fields": list(self.missing_fields),
            "manifest_hash_actual": self.manifest_hash_actual,
            "manifest_hash_expected": self.manifest_hash_expected,
        }


def _output_error_and_exit(output_format: str, msg: str, exit_code: int) -> NoReturn:
    """Mirror the family helper from sibling subcommand modules."""
    if output_format == "json":
        print(json.dumps({"success": False, "error": msg}))
    else:
        logger.error(msg)
    sys.exit(exit_code)


def _is_field_populated(value: Any) -> bool:
    """Return ``True`` when the operator clearly populated the field.

    Empty string / empty list / empty dict / ``None`` count as "the
    operator forgot" (a placeholder still in the auto-generation
    template), not "the operator chose to leave it empty".
    """
    if value is None:
        return False
    if isinstance(value, (str, list, dict)) and len(value) == 0:
        return False
    return True


def verify_annex_iv_artifact(path: str) -> VerifyAnnexIVResult:
    """Library entry: verify an Annex IV JSON file's completeness + manifest hash.

    Used by ``forgelm verify-annex-iv`` and exposed for integrators via
    the package facade.  Returns a structured result; never raises on
    documented failure modes (the caller decides whether to exit 1 or
    2 based on the result class).  Raises :class:`OSError` for genuine
    I/O failures on an existing file (dispatcher → ``EXIT_TRAINING_ERROR``)
    and :class:`json.JSONDecodeError` for parse failures (dispatcher →
    ``EXIT_CONFIG_ERROR`` since malformed JSON is a caller-input error).
    """
    with open(path, "r", encoding="utf-8") as fh:
        artifact = json.load(fh)

    if not isinstance(artifact, dict):
        return VerifyAnnexIVResult(
            valid=False,
            reason=f"Artifact root is {type(artifact).__name__}, expected JSON object.",
        )

    # Required fields: walk the static catalog so a future schema
    # addition is one row in the tuple, not a code edit at every
    # call site.
    missing: List[str] = []
    for key, _description in _ANNEX_IV_REQUIRED_FIELDS:
        if not _is_field_populated(artifact.get(key)):
            missing.append(key)
    if missing:
        return VerifyAnnexIVResult(
            valid=False,
            reason=f"Missing or empty required Annex IV field(s): {', '.join(missing)}.",
            missing_fields=missing,
        )

    # Manifest hash recompute (tampering detection).  When the artifact
    # carries `metadata.manifest_hash` we recompute SHA-256 over the
    # canonical-JSON representation of the artifact MINUS the metadata
    # block (which itself contains the hash) and compare.
    metadata = artifact.get("metadata") if isinstance(artifact.get("metadata"), dict) else None
    expected = metadata.get("manifest_hash") if metadata else None
    if expected:
        actual = _compute_manifest_hash(artifact)
        if actual != expected:
            return VerifyAnnexIVResult(
                valid=False,
                reason="Manifest hash mismatch — artifact may have been modified after generation.",
                manifest_hash_actual=actual,
                manifest_hash_expected=expected,
            )
        return VerifyAnnexIVResult(
            valid=True,
            reason="All Annex IV §1-9 fields populated; manifest hash matches.",
            manifest_hash_actual=actual,
            manifest_hash_expected=expected,
        )

    # No manifest hash present — the field-completeness check is the
    # only signal we can give.  Pass with a note so the operator knows.
    return VerifyAnnexIVResult(
        valid=True,
        reason="All Annex IV §1-9 fields populated; no manifest_hash present so tampering detection skipped.",
    )


def _compute_manifest_hash(artifact: Dict[str, Any]) -> str:
    """Recompute the manifest hash the same way ``compliance.py`` writes it.

    Delegates to :func:`forgelm.compliance.compute_annex_iv_manifest_hash`
    so the writer + verifier canonicalisation cannot drift byte-for-byte.
    Wave 2b Round-4 review F-W2B-05 fix: the previous local
    implementation duplicated the canonicalisation logic; if the writer
    ever changed (added a new metadata key, switched separators, etc.)
    legitimate artefacts would fail their own verifier.
    """
    from forgelm.compliance import compute_annex_iv_manifest_hash

    return compute_annex_iv_manifest_hash(artifact)


def _run_verify_annex_iv_cmd(args, output_format: str) -> None:
    """Top-level dispatcher for ``forgelm verify-annex-iv <path>``.

    Two modes:

    - **Single artefact** (default): ``<path>`` is an Annex IV JSON file
      and the verifier checks field completeness + manifest hash.
    - **Pipeline** (``--pipeline`` flag): ``<path>`` is a pipeline run
      directory and the verifier reads
      ``<path>/compliance/pipeline_manifest.json`` and runs chain-
      integrity + stage-index + ``stopped_at`` coherence + per-stage
      training_manifest existence checks.  Returns a list of violations
      and exits 0 only when the list is empty.
    """
    path = getattr(args, "path", None)
    if not path:
        _output_error_and_exit(
            output_format,
            "verify-annex-iv requires a path argument: `forgelm verify-annex-iv <annex_iv.json>`.",
            EXIT_CONFIG_ERROR,
        )

    # Phase 14: ``--pipeline`` mode validates the chain-level manifest.
    if getattr(args, "pipeline", False):
        from forgelm.compliance import verify_pipeline_manifest_at_path

        violations = verify_pipeline_manifest_at_path(path)
        if output_format == "json":
            print(
                json.dumps(
                    {
                        "success": not violations,
                        "mode": "pipeline",
                        "path": os.path.abspath(path),
                        "violations": violations,
                    },
                    indent=2,
                )
            )
        else:
            if not violations:
                print(f"OK: pipeline manifest at {path}")
            else:
                print(f"FAIL: pipeline manifest at {path}")
                for v in violations:
                    print(f"  - {v}")
        sys.exit(EXIT_SUCCESS if not violations else EXIT_CONFIG_ERROR)

    # Round 6 absorption: the prior `os.path.isfile()` pre-check
    # collapsed two distinct conditions ("path doesn't exist" and
    # "path exists but the user can't stat it") into a single
    # `EXIT_CONFIG_ERROR`, breaking the documented exit-code
    # contract for the permission-denied case.  Move all path
    # validation inside the try block and let Python's exception
    # hierarchy disambiguate: FileNotFoundError + IsADirectoryError
    # = caller-input error (exit 1); OSError (incl. PermissionError)
    # = genuine I/O failure on a reachable path (exit 2).
    try:
        result = verify_annex_iv_artifact(path)
    except (FileNotFoundError, IsADirectoryError) as exc:
        # Caller-input error: the path is missing or refers to a
        # directory.  Per docs/standards/error-handling.md and the
        # public exit-code contract in
        # docs/reference/verify_annex_iv_subcommand.md, this is
        # exit 1 (config / caller error).
        _output_error_and_exit(
            output_format,
            f"Annex IV artifact not found or not a regular file: {path!r} ({exc.__class__.__name__}).",
            EXIT_CONFIG_ERROR,
        )
    except json.JSONDecodeError as exc:
        # Validation failure: the artifact is reachable but not parseable
        # as JSON.  Operator-actionable input error per the public
        # contract; routes to exit 1.
        _output_error_and_exit(
            output_format,
            f"Annex IV artifact at {path!r} is not valid JSON: {exc.msg} (line {exc.lineno}).",
            EXIT_CONFIG_ERROR,
        )
    except OSError as exc:
        # Genuine runtime I/O failure on a reachable path (permission
        # denied, mid-read I/O error, locked file, etc.).  This is the
        # post-FileNotFoundError catch-all because Python's OSError
        # hierarchy puts FileNotFoundError as a subclass — order
        # matters.
        _output_error_and_exit(
            output_format,
            f"Could not read Annex IV artifact {path!r}: {exc}.",
            EXIT_TRAINING_ERROR,
        )

    payload = result.to_dict()
    payload["path"] = os.path.abspath(path)
    if output_format == "json":
        print(json.dumps({"success": result.valid, **payload}, indent=2))
    else:
        if result.valid:
            print(f"OK: {path}")
            print(f"  {result.reason}")
        else:
            print(f"FAIL: {path}")
            print(f"  {result.reason}")
            for missing in result.missing_fields:
                print(f"    - missing: {missing}")
    sys.exit(EXIT_SUCCESS if result.valid else EXIT_CONFIG_ERROR)


__all__ = [
    "VerifyAnnexIVResult",
    "_run_verify_annex_iv_cmd",
    "verify_annex_iv_artifact",
]
