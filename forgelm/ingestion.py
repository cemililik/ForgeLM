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
from typing import Callable, Iterable, List, Optional, Tuple

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
    extra_notes: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Format extractors — each returns the document's plain text or raises
# ---------------------------------------------------------------------------


def _extract_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover — covered by extras
        raise ImportError(
            "PDF ingestion requires the 'ingestion' extra. Install with: pip install 'forgelm[ingestion]'"
        ) from exc

    reader = PdfReader(str(path))
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
    paragraphs = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
    return "\n\n".join(paragraphs)


def _extract_epub(path: Path) -> str:
    try:
        from bs4 import BeautifulSoup
        from ebooklib import ITEM_DOCUMENT, epub
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "EPUB ingestion requires the 'ingestion' extra. Install with: pip install 'forgelm[ingestion]'"
        ) from exc

    book = epub.read_epub(str(path))
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
    return path.read_text(encoding="utf-8", errors="replace")


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
    if not text:
        return
    step = chunk_size - overlap
    for start in range(0, len(text), step):
        chunk = text[start : start + chunk_size]
        if chunk.strip():
            yield chunk


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
        overlap: Overlap window for the sliding strategy. Must be < ``chunk_size``.
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
        from .data_audit import mask_pii
    else:
        mask_pii = None  # type: ignore[assignment]

    files = list(_iter_input_files(src, recursive))
    if not files:
        raise FileNotFoundError(f"No supported files found at '{src}' (extensions: {', '.join(SUPPORTED_EXTENSIONS)}).")

    chunk_count = 0
    files_processed = 0
    files_skipped = 0
    total_chars = 0
    format_counts: dict = {}
    notes: List[str] = []

    with open(dst, "w", encoding=encoding) as out_fh:
        for fpath in files:
            extractor = _select_extractor(fpath)
            if extractor is None:
                files_skipped += 1
                continue
            try:
                text = extractor(fpath)
            except ImportError:
                raise
            except Exception as exc:
                logger.warning("Skipping '%s' (extraction failed): %s", fpath, exc)
                files_skipped += 1
                continue

            if not text or not text.strip():
                files_skipped += 1
                logger.warning("Skipping '%s' (no extractable text).", fpath)
                continue

            files_processed += 1
            ext = fpath.suffix.lower()
            format_counts[ext] = format_counts.get(ext, 0) + 1

            for chunk in _strategy_dispatch(strategy, text, chunk_size, overlap):
                payload = chunk.strip()
                if not payload:
                    continue
                if mask_pii is not None:
                    payload = mask_pii(payload)
                out_fh.write(json.dumps({"text": payload}, ensure_ascii=False) + "\n")
                chunk_count += 1
                total_chars += len(payload)

    if files_skipped:
        notes.append(f"skipped {files_skipped} file(s) — see warnings above")
    if pii_mask:
        notes.append("PII masking enabled — detected spans replaced with [REDACTED]")

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
