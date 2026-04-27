"""Document ingestion — turn raw files (PDF/DOCX/EPUB/TXT) into SFT-ready JSONL.

Phase 11 (Document Ingestion) — bridges raw enterprise corpora (legal, medical,
policy manuals) to ForgeLM's training data format without forcing operators to
write custom preprocessing.

Output shape is the ``{"text": "<chunk>"}`` JSONL ForgeLM's data loader already
recognizes as pre-formatted SFT input (see ``forgelm/data.py``). Pair with
``forgelm --generate-data`` if you want the chunks expanded into Q&A
``messages`` form via a teacher model.

Optional extra:

    pip install 'forgelm[ingestion]'

OCR is out of scope. PDFs without a text layer produce a warning and zero
chunks; pre-process with Tesseract / AWS Textract before ingest.

Public API:

* :class:`IngestionResult` — outcome dataclass
* :func:`ingest_path` — single file or directory → JSONL
* :func:`list_supported_formats` — informational helper for the CLI
* :func:`describe_strategies` — chunking strategy descriptions
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger("forgelm.ingestion")


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


SUPPORTED_EXTENSIONS: Tuple[str, ...] = (".pdf", ".docx", ".epub", ".txt", ".md")


CHUNK_STRATEGIES: Tuple[str, ...] = ("sliding", "paragraph", "semantic")


@dataclass
class IngestionResult:
    """Summary of an ``ingest_path`` run."""

    output_path: Path
    chunk_count: int
    files_processed: int
    files_skipped: int
    total_chars: int
    format_counts: dict = field(default_factory=dict)
    pii_redaction_counts: dict = field(default_factory=dict)
    extra_notes: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Format extractors — each returns the document's plain text or raises
# ---------------------------------------------------------------------------


def _extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
        from pypdf.errors import DependencyError, FileNotDecryptedError
    except ImportError as exc:  # pragma: no cover — covered by extras
        raise ImportError(
            "PDF ingestion requires the 'ingestion' extra. Install with: pip install 'forgelm[ingestion]'"
        ) from exc

    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        raise ValueError(f"Could not open PDF '{path}': {exc}") from exc

    if getattr(reader, "is_encrypted", False):
        # Try empty password — common for owner-encrypted PDFs that are still
        # readable. If the user has a password, document the recommended path
        # (decrypt externally with qpdf / pdftk) rather than wiring a CLI flag.
        try:
            reader.decrypt("")
        except (FileNotDecryptedError, NotImplementedError, DependencyError) as exc:
            raise ValueError(
                f"PDF '{path}' is encrypted. Decrypt it first (qpdf --decrypt / pdftk input_pw …) and re-run ingest."
            ) from exc
        if getattr(reader, "is_encrypted", False):
            raise ValueError(f"PDF '{path}' is encrypted with a non-empty password. Decrypt externally before ingest.")

    pages: List[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            logger.debug("PDF page extraction failed for %s: %s", path, exc)
            text = ""
        if text.strip():
            pages.append(text)
    if not pages:
        logger.warning(
            "No extractable text in '%s'. Likely a scanned PDF without a text layer; "
            "run OCR (Tesseract / AWS Textract) before ingest.",
            path,
        )
    return "\n\n".join(pages)


def _extract_docx(path: Path) -> str:
    try:
        from docx import Document
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "DOCX ingestion requires the 'ingestion' extra. Install with: pip install 'forgelm[ingestion]'"
        ) from exc

    doc = Document(str(path))
    blocks: List[str] = [p.text for p in doc.paragraphs if p.text and p.text.strip()]

    # Tables — flatten cell text in row-major order so the structure isn't
    # lost outright. Matches the "DOCX tables are flattened to plain text"
    # behavior promised in docs/guides/ingestion.md. Empty cells skipped.
    for table in doc.tables:
        for row in table.rows:
            row_cells = [cell.text.strip() for cell in row.cells if cell.text and cell.text.strip()]
            if row_cells:
                blocks.append(" | ".join(row_cells))

    return "\n\n".join(blocks)


def _extract_epub(path: Path) -> str:
    try:
        from bs4 import BeautifulSoup
        from ebooklib import ITEM_DOCUMENT, epub
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "EPUB ingestion requires the 'ingestion' extra. Install with: pip install 'forgelm[ingestion]'"
        ) from exc

    # ebooklib >= 0.18 emits deprecation warnings unless `options=` is passed
    # explicitly. ignore_ncx=True silences the noisy NCX (table of contents)
    # warning that adds nothing for ingestion. ignore_missing_css avoids
    # CSS-resolution warnings on EPUBs that ship broken stylesheets.
    book = epub.read_epub(
        str(path),
        options={"ignore_ncx": True, "ignore_missing_css": True},
    )
    chunks: List[str] = []
    for item in book.get_items():
        if item.get_type() != ITEM_DOCUMENT:
            continue
        soup = BeautifulSoup(item.get_content(), "html.parser")
        text = soup.get_text(separator="\n").strip()
        if text:
            chunks.append(text)
    return "\n\n".join(chunks)


def _extract_text(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    # Detect binary contamination — files mis-routed through the .txt extension
    # (e.g. unzipped binaries renamed) come back as a sea of U+FFFD replacement
    # characters. Below 1% is normal for legacy encodings; above is suspicious.
    if raw:
        replacement_count = raw.count("�")
        if replacement_count / max(len(raw), 1) > 0.01:
            logger.warning(
                "'%s' contains %d Unicode replacement chars (%.1f%% of file). "
                "Likely binary content masquerading as text — verify the file is actually UTF-8.",
                path,
                replacement_count,
                replacement_count * 100 / len(raw),
            )
    return raw


_EXTRACTORS: dict = {
    ".pdf": _extract_pdf,
    ".docx": _extract_docx,
    ".epub": _extract_epub,
    ".txt": _extract_text,
    ".md": _extract_text,
}


# ---------------------------------------------------------------------------
# Chunking strategies — each yields chunk strings from raw text
# ---------------------------------------------------------------------------


def _chunk_sliding(text: str, chunk_size: int, overlap: int) -> Iterable[str]:
    """Fixed character window with overlap. Coarse but predictable."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be in [0, chunk_size)")
    # Reject pathological overlap up front: ratios above 0.5 explode chunk
    # count (overlap=199 with chunk_size=200 yields ~one chunk per character).
    # The safety net is preventative — without it a typo can produce a
    # multi-million-line JSONL silently.
    if overlap > chunk_size // 2:
        raise ValueError(
            f"overlap ({overlap}) must be at most chunk_size // 2 ({chunk_size // 2}) to avoid quadratic chunk count. "
            "Reduce --overlap or increase --chunk-size."
        )
    if not text:
        return
    step = chunk_size - overlap
    for start in range(0, len(text), step):
        chunk = text[start : start + chunk_size]
        if chunk.strip():
            yield chunk
        # Stop once the current window already covers end-of-text. Without
        # this guard, large `--overlap` produces runt trailing chunks that
        # are pure prefixes of the prior chunk — they pollute the JSONL
        # with semantically-empty rows and skew the audit's near-duplicate
        # / length stats.
        if start + chunk_size >= len(text):
            return


def _chunk_paragraph(text: str, max_chunk_size: int) -> Iterable[str]:
    """Greedy paragraph packer — never splits a paragraph mid-sentence.

    Paragraphs longer than ``max_chunk_size`` are emitted on their own
    (caller's chunk_size becomes a soft cap). Keeps sentence boundaries
    intact so SFT examples don't start mid-thought.
    """
    if max_chunk_size <= 0:
        raise ValueError("max_chunk_size must be positive")
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return

    current: List[str] = []
    current_len = 0
    for para in paragraphs:
        para_len = len(para)
        if current_len + para_len + 2 <= max_chunk_size or not current:
            current.append(para)
            current_len += para_len + 2
        else:
            yield "\n\n".join(current)
            current = [para]
            current_len = para_len
    if current:
        yield "\n\n".join(current)


def _chunk_semantic(text: str, chunk_size: int) -> Iterable[str]:
    raise NotImplementedError(
        "Semantic chunking requires an embedding model and is planned for a "
        "follow-up phase. Use 'sliding' or 'paragraph' for now."
    )


def _strategy_dispatch(strategy: str, text: str, chunk_size: int, overlap: int) -> Iterable[str]:
    if strategy == "sliding":
        return _chunk_sliding(text, chunk_size, overlap)
    if strategy == "paragraph":
        return _chunk_paragraph(text, chunk_size)
    if strategy == "semantic":
        return _chunk_semantic(text, chunk_size)
    raise ValueError(f"Unknown chunking strategy '{strategy}'. Choose from: {', '.join(CHUNK_STRATEGIES)}")


# ---------------------------------------------------------------------------
# File discovery + ingestion entry point
# ---------------------------------------------------------------------------


def _iter_input_files(input_path: Path, recursive: bool) -> Iterable[Path]:
    if input_path.is_file():
        yield input_path
        return
    if not input_path.is_dir():
        raise FileNotFoundError(f"Input path does not exist: {input_path}")
    pattern = "**/*" if recursive else "*"
    for entry in sorted(input_path.glob(pattern)):
        if entry.is_file() and entry.suffix.lower() in SUPPORTED_EXTENSIONS:
            yield entry


def _select_extractor(path: Path) -> Optional[Callable[[Path], str]]:
    return _EXTRACTORS.get(path.suffix.lower())


def list_supported_formats() -> List[str]:
    """Return the list of file extensions ingest_path can handle."""
    return list(SUPPORTED_EXTENSIONS)


def describe_strategies() -> List[Tuple[str, str]]:
    """Return ``(name, one-line description)`` for every chunking strategy."""
    return [
        ("sliding", "Fixed-size character window with overlap. Predictable, coarse."),
        ("paragraph", "Greedy paragraph packer; never splits a paragraph. Preserves boundaries."),
        ("semantic", "Embedding-clustered (NotImplementedError today; planned for a follow-up phase)."),
    ]


@dataclass
class _FileOutcome:
    """Per-file aggregate emitted by :func:`_process_one_file`."""

    chunks_written: int = 0
    chars_written: int = 0
    file_processed: bool = False
    file_skipped: bool = False
    extension: Optional[str] = None
    pii_counts: Dict[str, int] = field(default_factory=dict)


def _process_one_file(
    fpath: Path,
    out_fh: Any,
    *,
    strategy: str,
    chunk_size: int,
    overlap: int,
    mask_pii: Optional[Callable[..., Any]],
) -> _FileOutcome:
    """Extract → chunk → optionally mask → emit JSONL for a single file.

    ImportError propagates (missing optional extra is not a per-file skip).
    Any other extraction failure is logged + counted as a skip.
    """
    extractor = _select_extractor(fpath)
    if extractor is None:
        return _FileOutcome(file_skipped=True)

    try:
        text = extractor(fpath)
    except ImportError:
        # ImportError must propagate — missing extras are not a per-file
        # skip. The CLI wrapper turns this into EXIT_TRAINING_ERROR +
        # an install-hint message.
        raise
    except Exception as exc:
        logger.warning("Skipping '%s' (extraction failed): %s", fpath, exc)
        return _FileOutcome(file_skipped=True)

    if not text or not text.strip():
        logger.warning("Skipping '%s' (no extractable text).", fpath)
        return _FileOutcome(file_skipped=True)

    outcome = _FileOutcome(file_processed=True, extension=fpath.suffix.lower())
    for chunk in _strategy_dispatch(strategy, text, chunk_size, overlap):
        payload = chunk.strip()
        if not payload:
            continue
        if mask_pii is not None:
            # Get the masked text + per-type counts in a single pass.
            # Counting via detect_pii beforehand would double-count
            # spans matched by multiple patterns; mask_pii's own
            # first-match-wins precedence gives the truthful count.
            payload, redaction_counts = mask_pii(payload, return_counts=True)
            for kind, count in redaction_counts.items():
                outcome.pii_counts[kind] = outcome.pii_counts.get(kind, 0) + count
        out_fh.write(json.dumps({"text": payload}, ensure_ascii=False) + "\n")
        outcome.chunks_written += 1
        outcome.chars_written += len(payload)
    return outcome


def ingest_path(
    input_path: str,
    *,
    output_path: str,
    chunk_size: int = 2048,
    overlap: int = 200,
    strategy: str = "paragraph",
    recursive: bool = False,
    pii_mask: bool = False,
    encoding: str = "utf-8",
) -> IngestionResult:
    """Ingest a single file or a directory tree into a SFT-compatible JSONL.

    Args:
        input_path: File or directory to ingest.
        output_path: Where to write the ``.jsonl`` output. Parents are created.
        chunk_size: Soft size cap per chunk (characters).
        overlap: Overlap window for the sliding strategy. Must satisfy
            both ``overlap < chunk_size`` AND ``overlap <= chunk_size // 2``.
            The half-chunk cap prevents quadratic chunk explosion: an
            ``overlap`` of 199 with ``chunk_size`` 200 would emit roughly
            one chunk per character. ``_chunk_sliding`` raises
            ``ValueError`` when either bound is violated.
        strategy: One of ``sliding`` / ``paragraph`` / ``semantic``.
        recursive: When ``input_path`` is a directory, walk subdirectories too.
        pii_mask: Replace detected PII spans with ``[REDACTED]`` before writing.
        encoding: Output encoding (default UTF-8).

    Returns:
        :class:`IngestionResult` summarizing the run.

    Raises:
        FileNotFoundError: ``input_path`` does not exist.
        ValueError: invalid chunking parameters.
        ImportError: optional extras not installed for the format being ingested.
    """
    src = Path(input_path).expanduser().resolve()
    dst = Path(output_path).expanduser().resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)

    if pii_mask:
        # Lazy import: PII helpers live in data_audit.py; we don't want to
        # pay the audit module's import cost when masking is off.
        from .data_audit import mask_pii as _mask_pii

        mask_pii_fn: Optional[Callable[..., Any]] = _mask_pii
    else:
        mask_pii_fn = None

    files = list(_iter_input_files(src, recursive))
    if not files:
        raise FileNotFoundError(f"No supported files found at '{src}' (extensions: {', '.join(SUPPORTED_EXTENSIONS)}).")

    chunk_count = 0
    files_processed = 0
    files_skipped = 0
    total_chars = 0
    format_counts: dict = {}
    pii_redaction_counts: dict = {}
    notes: List[str] = []

    # newline="\n" pins LF on Windows. JSONL Files spec requires LF, and
    # piping through tooling (jq -c, wc -l, downstream HF dataset loaders)
    # avoids CRLF surprises. Linux/macOS default is already LF.
    with open(dst, "w", encoding=encoding, newline="\n") as out_fh:
        for fpath in files:
            outcome = _process_one_file(
                fpath,
                out_fh,
                strategy=strategy,
                chunk_size=chunk_size,
                overlap=overlap,
                mask_pii=mask_pii_fn,
            )
            chunk_count += outcome.chunks_written
            total_chars += outcome.chars_written
            if outcome.file_processed:
                files_processed += 1
                if outcome.extension:
                    format_counts[outcome.extension] = format_counts.get(outcome.extension, 0) + 1
            if outcome.file_skipped:
                files_skipped += 1
            for kind, count in outcome.pii_counts.items():
                pii_redaction_counts[kind] = pii_redaction_counts.get(kind, 0) + count

    if files_skipped:
        notes.append(f"skipped {files_skipped} file(s) — see warnings above")
    if pii_mask:
        if pii_redaction_counts:
            redacted_total = sum(pii_redaction_counts.values())
            breakdown = ", ".join(f"{k}={v}" for k, v in sorted(pii_redaction_counts.items()))
            notes.append(f"PII masking redacted {redacted_total} span(s): {breakdown}")
        else:
            notes.append("PII masking enabled — no PII detected in this corpus")

    logger.info(
        "ingest: source=%s output=%s files=%d chunks=%d chars=%d strategy=%s",
        src,
        dst,
        files_processed,
        chunk_count,
        total_chars,
        strategy,
    )

    return IngestionResult(
        output_path=dst,
        chunk_count=chunk_count,
        files_processed=files_processed,
        files_skipped=files_skipped,
        total_chars=total_chars,
        format_counts=format_counts,
        pii_redaction_counts=pii_redaction_counts,
        extra_notes=notes,
    )


def summarize_result(result: IngestionResult) -> str:
    """Render an :class:`IngestionResult` as a multi-line operator-friendly report."""
    lines = [
        "Ingestion summary",
        f"  Output JSONL  : {result.output_path}",
        f"  Files (in/out): processed={result.files_processed}  skipped={result.files_skipped}",
        f"  Chunks        : {result.chunk_count}",
        f"  Total chars   : {result.total_chars}",
    ]
    if result.format_counts:
        per_fmt = ", ".join(f"{ext.lstrip('.')}={n}" for ext, n in sorted(result.format_counts.items()))
        lines.append(f"  By format     : {per_fmt}")
    for note in result.extra_notes:
        lines.append(f"  Note          : {note}")
    lines.append("")
    lines.append(f"Next: forgelm --data-audit {result.output_path} --output ./audit/")
    lines.append(
        f"Or train: forgelm --config <your.yaml>  (set data.dataset_name_or_path: {os.fspath(result.output_path)})"
    )
    return "\n".join(lines)
