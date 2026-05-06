"""``forgelm ingest`` dispatcher (Phase 11 raw-document → JSONL flow)."""

from __future__ import annotations

import json
import sys

from .._exit_codes import EXIT_CONFIG_ERROR, EXIT_TRAINING_ERROR
from .._logging import logger


def _run_ingest_cmd(args, output_format: str) -> None:
    """Phase 11 dispatch: raw documents → SFT-ready JSONL."""
    # Phase 12.5: --all-mask is a shorthand that ORs into the two individual
    # masking flags. Resolve it here at the CLI boundary so ``ingest_path``
    # keeps its narrow API (only ``pii_mask`` / ``secrets_mask`` booleans).
    all_mask = getattr(args, "all_mask", False)
    pii_mask = bool(getattr(args, "pii_mask", False)) or all_mask
    secrets_mask = bool(getattr(args, "secrets_mask", False)) or all_mask

    # Lazy import: ``forgelm.ingestion`` is kept out of module top-level so
    # ``import forgelm.cli`` (run on every console-script invocation, including
    # ``forgelm --help``) does not eagerly pull the ingestion package — and its
    # transitive optional-dependency probes — into ``sys.modules``. The three
    # names are imported together *before* the try-block so that
    # ``OptionalDependencyError`` is guaranteed to be bound when the
    # ``except`` clause runs; if the import itself fails it propagates as a
    # plain ``ImportError`` (a real bug, not an operator-facing condition).
    from ...ingestion import OptionalDependencyError, ingest_path, summarize_result

    try:
        result = ingest_path(
            args.input_path,
            output_path=args.output,
            chunk_size=args.chunk_size,
            overlap=args.overlap,
            strategy=args.strategy,
            recursive=args.recursive,
            pii_mask=pii_mask,
            secrets_mask=secrets_mask,
            chunk_tokens=getattr(args, "chunk_tokens", None),
            overlap_tokens=getattr(args, "overlap_tokens", 0),
            tokenizer=getattr(args, "tokenizer", None),
        )
    except (
        FileNotFoundError,  # NOSONAR — OSError subclass; listed explicitly so the error type is visible to readers
        ValueError,
        PermissionError,  # NOSONAR — OSError subclass; listed explicitly so the error type is visible to readers
        IsADirectoryError,  # NOSONAR — OSError subclass; listed explicitly so the error type is visible to readers
        OSError,
    ) as exc:
        # FileNotFoundError / PermissionError / IsADirectoryError are all
        # OSError subclasses, but listed explicitly so the error class is
        # visible to readers; OSError covers ENOSPC, broken-symlink walk
        # failures, and locked-file open() errors that would otherwise leak
        # through with a confusing traceback. ValueError stays first because
        # ingest_path raises it for invalid chunking parameters before any
        # filesystem access.
        if output_format == "json":
            print(json.dumps({"success": False, "error": str(exc)}))
        else:
            logger.error("Ingest failed: %s", exc)
        sys.exit(EXIT_CONFIG_ERROR)
    except OptionalDependencyError as exc:
        # Catch the narrow optional-extras subclass only.  Plain ``ImportError``
        # would mask genuine bugs (e.g. an internal forgelm import error) under
        # the same install-hint envelope; letting those propagate preserves the
        # original traceback for the operator.  Convention across subcommands:
        # a missing optional extra is a *runtime* failure of the dispatched
        # feature, not a config validation failure — exit with
        # EXIT_TRAINING_ERROR so CI/CD retry logic treats it the same way.
        if output_format == "json":
            print(json.dumps({"success": False, "error": str(exc)}))
        else:
            logger.error("%s", exc)
        sys.exit(EXIT_TRAINING_ERROR)

    if output_format == "json":
        print(
            json.dumps(
                {
                    "success": True,
                    "output_path": str(result.output_path),
                    "chunk_count": result.chunk_count,
                    "files_processed": result.files_processed,
                    "files_skipped": result.files_skipped,
                    "total_chars": result.total_chars,
                    "format_counts": result.format_counts,
                    "pii_redaction_counts": result.pii_redaction_counts,
                    "secrets_redaction_counts": result.secrets_redaction_counts,
                    "pdf_header_footer_lines_stripped": result.pdf_header_footer_lines_stripped,
                    "notes": result.extra_notes,
                    "notes_structured": result.notes_structured,
                },
                indent=2,
            )
        )
    else:
        print(summarize_result(result))
