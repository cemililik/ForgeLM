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
from collections import Counter
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
    """Summary of an ``ingest_path`` run.

    Both :attr:`extra_notes` (free-text, operator-friendly) and
    :attr:`notes_structured` (programmatic ``{key: value}``) are emitted
    so machine-driven pipelines do not need to regex-match the prose. The
    structured payload is stable across releases; the free-text list is
    for human consumption and may rephrase the same facts.
    """

    output_path: Path
    chunk_count: int
    files_processed: int
    files_skipped: int
    total_chars: int
    format_counts: dict = field(default_factory=dict)
    pii_redaction_counts: dict = field(default_factory=dict)
    extra_notes: List[str] = field(default_factory=list)
    notes_structured: Dict[str, Any] = field(default_factory=dict)
    pdf_header_footer_lines_stripped: int = 0


# ---------------------------------------------------------------------------
# Format extractors — each returns the document's plain text or raises
# ---------------------------------------------------------------------------


_PDF_REPEAT_MIN_PAGES: int = 3
_PDF_REPEAT_THRESHOLD: float = 0.7


def _repeating_edge_lines(page_lines: List[List[str]], cutoff: int) -> Tuple[set, set]:
    """Return (repeating_first_lines, repeating_last_lines) at this pass."""
    first_counts: Counter = Counter(lines[0] for lines in page_lines if lines)
    last_counts: Counter = Counter(lines[-1] for lines in page_lines if lines)
    return (
        {ln for ln, n in first_counts.items() if n >= cutoff},
        {ln for ln, n in last_counts.items() if n >= cutoff},
    )


def _pop_repeating_edges(
    page_lines: List[List[str]],
    repeating_firsts: set,
    repeating_lasts: set,
) -> int:
    """Pop the leading / trailing repeating line from each page; return total stripped."""
    stripped = 0
    for lines in page_lines:
        if lines and lines[0] in repeating_firsts:
            lines.pop(0)
            stripped += 1
        if lines and lines[-1] in repeating_lasts:
            lines.pop()
            stripped += 1
    return stripped


def _strip_repeating_page_lines(pages: List[str]) -> Tuple[List[str], int]:
    """Strip leading / trailing lines that repeat across pages.

    Page-level headers (company watermark, document title) and footers
    (page number text, copyright line) end up as the first / last line
    of every page after :func:`_extract_pdf` and inflate near-duplicate
    counts during the audit. We iterate: at each pass we collect the
    first and last non-empty line of every page, find lines that recur
    in ≥ 70 % of pages (default), and pop those from the start / end of
    every page. The pass repeats until no more lines meet the threshold,
    so multi-line headers (e.g. ``Line 1: company name`` followed by
    ``Line 2: CONFIDENTIAL``) are stripped fully rather than leaving the
    second line stranded as a new "first line" that no longer matches
    the original count.

    Returns:
        ``(cleaned_pages, lines_stripped)``. Caller can roll the count
        into structured ingestion notes for downstream visibility.

    The dedup is a no-op on documents with fewer than 3 pages — the
    statistical signal is too weak to distinguish "header" from
    "actual repeated paragraph".
    """
    if len(pages) < _PDF_REPEAT_MIN_PAGES:
        return pages, 0

    page_lines: List[List[str]] = [[ln.strip() for ln in p.splitlines() if ln.strip()] for p in pages]
    cutoff = max(2, int(_PDF_REPEAT_THRESHOLD * len(pages)))
    total_stripped = 0

    while True:
        repeating_firsts, repeating_lasts = _repeating_edge_lines(page_lines, cutoff)
        if not repeating_firsts and not repeating_lasts:
            break
        stripped = _pop_repeating_edges(page_lines, repeating_firsts, repeating_lasts)
        if stripped == 0:
            # Edge case: the only repeating line was already alone on a
            # short page, so popping it left fewer pages than ``cutoff``
            # — break instead of looping with no work.
            break
        total_stripped += stripped

    cleaned = ["\n".join(lines) for lines in page_lines if lines]
    return cleaned, total_stripped


def _try_pdf_decrypt(reader: Any, path: Path) -> None:
    """Attempt empty-password decrypt for owner-encrypted PDFs; raise ValueError otherwise.

    Empty-password decrypt covers the common "owner-encrypted but readable"
    case. When that fails OR the reader still reports encrypted afterwards,
    we surface a clear message pointing the operator to external tooling
    (qpdf / pdftk) — wiring a CLI password flag would put credentials in
    shell history, which is the wrong default.
    """
    from pypdf.errors import DependencyError, FileNotDecryptedError

    try:
        reader.decrypt("")
    except (FileNotDecryptedError, NotImplementedError, DependencyError) as exc:
        raise ValueError(
            f"PDF '{path}' is encrypted. Decrypt it first (qpdf --decrypt / pdftk input_pw …) and re-run ingest."
        ) from exc
    if getattr(reader, "is_encrypted", False):
        raise ValueError(f"PDF '{path}' is encrypted with a non-empty password. Decrypt externally before ingest.")


def _read_pdf_pages(reader: Any, path: Path) -> List[str]:
    """Extract per-page text; tolerate page-level failures with a debug log."""
    pages: List[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            logger.debug("PDF page extraction failed for %s: %s", path, exc)
            text = ""
        if text.strip():
            pages.append(text)
    return pages


def _extract_pdf(path: Path, *, dedup_state: Optional[Dict[str, int]] = None) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover — covered by extras
        raise ImportError(
            "PDF ingestion requires the 'ingestion' extra. Install with: pip install 'forgelm[ingestion]'"
        ) from exc

    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        raise ValueError(f"Could not open PDF '{path}': {exc}") from exc

    if getattr(reader, "is_encrypted", False):
        _try_pdf_decrypt(reader, path)

    pages = _read_pdf_pages(reader, path)
    if not pages:
        logger.warning(
            "No extractable text in '%s'. Likely a scanned PDF without a text layer; "
            "run OCR (Tesseract / AWS Textract) before ingest.",
            path,
        )
        return ""

    cleaned_pages, stripped = _strip_repeating_page_lines(pages)
    if dedup_state is not None and stripped:
        # Roll into the run-level structured notes so the operator can
        # tell post-hoc that header/footer dedup was actually doing work.
        dedup_state["lines_stripped"] = dedup_state.get("lines_stripped", 0) + stripped
    return "\n\n".join(cleaned_pages)


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
# Phase 11.5: token-aware chunking (--chunk-tokens)
# ---------------------------------------------------------------------------


def _chunk_sliding_tokens(text: str, n_tokens: int, overlap_tokens: int, tokenizer: Any) -> Iterable[str]:
    """Sliding window measured in tokenizer tokens, not characters.

    Mirrors :func:`_chunk_sliding` (overlap clamped to half of the window
    to prevent quadratic chunk explosion) but tokens are the unit so the
    output sizes line up with ``model.max_length`` exactly.
    """
    if n_tokens <= 0:
        raise ValueError("chunk_tokens must be positive")
    if overlap_tokens < 0 or overlap_tokens >= n_tokens:
        raise ValueError("overlap_tokens must be in [0, chunk_tokens)")
    if overlap_tokens > n_tokens // 2:
        raise ValueError(
            f"overlap_tokens ({overlap_tokens}) must be at most chunk_tokens // 2 ({n_tokens // 2}) "
            "to avoid quadratic chunk count. Reduce --overlap-tokens or increase --chunk-tokens."
        )
    encoded = tokenizer.encode(text, add_special_tokens=False)
    if not encoded:
        return
    step = n_tokens - overlap_tokens
    for start in range(0, len(encoded), step):
        ids = encoded[start : start + n_tokens]
        if not ids:
            return
        decoded = tokenizer.decode(ids, skip_special_tokens=True)
        if decoded.strip():
            yield decoded
        if start + n_tokens >= len(encoded):
            return


def _chunk_paragraph_tokens(text: str, max_tokens: int, tokenizer: Any) -> Iterable[str]:
    """Greedy paragraph packer with a token-count cap.

    Same semantics as :func:`_chunk_paragraph` (paragraphs are the unit
    of indivisibility), but the soft cap is measured in tokens so the
    emitted chunks can't blow past ``model.max_length``. Paragraphs that
    exceed ``max_tokens`` on their own are still emitted whole — better
    than mid-sentence splits.

    Paragraph mode is **non-overlapping by design**. Sliding token-overlap
    would slice mid-paragraph and defeat the boundary-preservation
    invariant. Use ``--strategy sliding`` (with ``--overlap-tokens``) when
    overlap is required; the CLI logs an info note when ``overlap_tokens``
    is set alongside ``--strategy paragraph``.

    The ``"\\n\\n"`` separator is included in the budget — most BPE
    tokenizers map it to 1–2 tokens, so a chunk packed near the cap can
    overflow by ~tens of tokens without this accounting. ``sep_tokens``
    is computed once via the tokenizer and added when joining.
    """
    if max_tokens <= 0:
        raise ValueError("chunk_tokens must be positive")
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return

    sep_tokens = len(tokenizer.encode("\n\n", add_special_tokens=False))

    current: List[str] = []
    current_tokens = 0
    for para in paragraphs:
        para_tokens = len(tokenizer.encode(para, add_special_tokens=False))
        # When we already have packed paragraphs, joining adds a "\n\n"
        # which costs ``sep_tokens`` on top of the new paragraph itself.
        cost = para_tokens + (sep_tokens if current else 0)
        if current_tokens + cost <= max_tokens or not current:
            current.append(para)
            current_tokens += cost
        else:
            yield "\n\n".join(current)
            current = [para]
            current_tokens = para_tokens
    if current:
        yield "\n\n".join(current)


def _strategy_dispatch_tokens(
    strategy: str,
    text: str,
    *,
    chunk_tokens: int,
    overlap_tokens: int,
    tokenizer: Any,
) -> Iterable[str]:
    if strategy == "sliding":
        return _chunk_sliding_tokens(text, chunk_tokens, overlap_tokens, tokenizer)
    if strategy == "paragraph":
        return _chunk_paragraph_tokens(text, chunk_tokens, tokenizer)
    if strategy == "semantic":
        return _chunk_semantic(text, chunk_tokens)
    raise ValueError(f"Unknown chunking strategy '{strategy}'. Choose from: {', '.join(CHUNK_STRATEGIES)}")


def _load_tokenizer(model_name: str) -> Any:
    """Resolve ``model_name`` to an HF :class:`AutoTokenizer`.

    Lazy import keeps the ingestion module import-time small for users
    who never touch token-aware chunking. ``trust_remote_code`` is
    intentionally OFF — token-aware chunking should never need a custom
    tokenizer class, and turning it on here would let arbitrary HF Hub
    repos run code at ingestion time without a config audit.
    """
    from transformers import AutoTokenizer  # type: ignore

    return AutoTokenizer.from_pretrained(model_name, use_fast=True, trust_remote_code=False)


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


def _extract_text_for_ingest(
    fpath: Path,
    extractor: Callable[..., str],
    pdf_dedup_state: Optional[Dict[str, int]],
) -> Optional[str]:
    """Run ``extractor`` against ``fpath``; return ``None`` to mean "skip this file".

    ``ImportError`` re-propagates (missing optional extra is a *runtime*
    failure of the dispatched feature, not a per-file skip). All other
    exceptions log a warning and signal a skip — consistent with the
    silently-tolerant per-file model the CLI relies on.
    """
    try:
        if extractor is _extract_pdf:
            return _extract_pdf(fpath, dedup_state=pdf_dedup_state)
        return extractor(fpath)
    except ImportError:
        raise
    except Exception as exc:
        logger.warning("Skipping '%s' (extraction failed): %s", fpath, exc)
        return None


def _select_chunks_iter(
    text: str,
    *,
    strategy: str,
    chunk_size: int,
    overlap: int,
    chunk_tokens: Optional[int],
    overlap_tokens: int,
    tokenizer: Any,
) -> Iterable[str]:
    """Pick the token-aware or character-based chunker based on flags."""
    if chunk_tokens and tokenizer is not None:
        return _strategy_dispatch_tokens(
            strategy,
            text,
            chunk_tokens=chunk_tokens,
            overlap_tokens=overlap_tokens,
            tokenizer=tokenizer,
        )
    return _strategy_dispatch(strategy, text, chunk_size, overlap)


def _emit_chunk(
    payload: str,
    out_fh: Any,
    outcome: _FileOutcome,
    mask_pii: Optional[Callable[..., Any]],
) -> None:
    """Mask (optional), serialise, and write one chunk; update outcome counters."""
    if mask_pii is not None:
        # Get the masked text + per-type counts in a single pass. Counting
        # via detect_pii beforehand would double-count spans matched by
        # multiple patterns; mask_pii's own first-match-wins precedence
        # gives the truthful count.
        payload, redaction_counts = mask_pii(payload, return_counts=True)
        for kind, count in redaction_counts.items():
            outcome.pii_counts[kind] = outcome.pii_counts.get(kind, 0) + count
    out_fh.write(json.dumps({"text": payload}, ensure_ascii=False) + "\n")
    outcome.chunks_written += 1
    outcome.chars_written += len(payload)


def _process_one_file(
    fpath: Path,
    out_fh: Any,
    *,
    strategy: str,
    chunk_size: int,
    overlap: int,
    mask_pii: Optional[Callable[..., Any]],
    chunk_tokens: Optional[int] = None,
    overlap_tokens: int = 0,
    tokenizer: Any = None,
    pdf_dedup_state: Optional[Dict[str, int]] = None,
) -> _FileOutcome:
    """Extract → chunk → optionally mask → emit JSONL for a single file.

    ``chunk_tokens`` is honoured when set: token-aware chunking takes over
    via :func:`_strategy_dispatch_tokens`, and ``chunk_size`` becomes a
    fallback only when the tokenizer is missing. ``pdf_dedup_state`` is
    threaded into :func:`_extract_pdf` so cross-page header/footer dedup
    counts roll up into the run-level structured notes.

    ImportError propagates (missing optional extra is not a per-file skip).
    Any other extraction failure is logged + counted as a skip.
    """
    extractor = _select_extractor(fpath)
    if extractor is None:
        return _FileOutcome(file_skipped=True)

    text = _extract_text_for_ingest(fpath, extractor, pdf_dedup_state)
    if text is None:
        return _FileOutcome(file_skipped=True)
    if not text or not text.strip():
        logger.warning("Skipping '%s' (no extractable text).", fpath)
        return _FileOutcome(file_skipped=True)

    outcome = _FileOutcome(file_processed=True, extension=fpath.suffix.lower())
    chunks_iter = _select_chunks_iter(
        text,
        strategy=strategy,
        chunk_size=chunk_size,
        overlap=overlap,
        chunk_tokens=chunk_tokens,
        overlap_tokens=overlap_tokens,
        tokenizer=tokenizer,
    )
    for chunk in chunks_iter:
        payload = chunk.strip()
        if not payload:
            continue
        _emit_chunk(payload, out_fh, outcome, mask_pii)
    return outcome


DEFAULT_CHUNK_SIZE: int = 2048
"""Public default for the character-based chunk-size cap.

Exposed so the CLI default and the library default share a single source
of truth, and so the "did the operator pass --chunk-size explicitly?"
detection in :func:`ingest_path` is not a magic-number compare.
"""


def ingest_path(
    input_path: str,
    *,
    output_path: str,
    chunk_size: Optional[int] = None,
    overlap: int = 200,
    strategy: str = "paragraph",
    recursive: bool = False,
    pii_mask: bool = False,
    encoding: str = "utf-8",
    chunk_tokens: Optional[int] = None,
    overlap_tokens: int = 0,
    tokenizer: Optional[str] = None,
) -> IngestionResult:
    """Ingest a single file or a directory tree into a SFT-compatible JSONL.

    Args:
        input_path: File or directory to ingest.
        output_path: Where to write the ``.jsonl`` output. Parents are created.
        chunk_size: Soft size cap per chunk (characters). ``None`` means
            "use the library default" (:data:`DEFAULT_CHUNK_SIZE`). When
            ``chunk_tokens`` is set the value is ignored, and a warning is
            logged only when the operator passed an *explicit* ``chunk_size``
            so stale CLI invocations are visible without spamming the
            common case.
        overlap: Overlap window for the sliding strategy in characters.
            Must satisfy both ``overlap < chunk_size`` AND
            ``overlap <= chunk_size // 2``. The half-chunk cap prevents
            quadratic chunk explosion. ``_chunk_sliding`` raises
            ``ValueError`` when either bound is violated.
        strategy: One of ``sliding`` / ``paragraph`` / ``semantic``.
        recursive: When ``input_path`` is a directory, walk subdirectories too.
        pii_mask: Replace detected PII spans with ``[REDACTED]`` before writing.
        encoding: Output encoding (default UTF-8).
        chunk_tokens: Phase 11.5 token-aware mode. When set, chunks are
            sized against the supplied ``tokenizer`` (in tokens), not
            characters. Use this when the operator's downstream model has
            a hard ``max_length`` budget and char-based sizing keeps
            tripping it.
        overlap_tokens: Sliding-window overlap measured in tokens. Same
            half-window cap as the character-based ``overlap``. Ignored
            when ``strategy="paragraph"`` (paragraph chunks are
            non-overlapping by design); a warning is logged in that case.
        tokenizer: HuggingFace model name resolved via :class:`AutoTokenizer`.
            Required when ``chunk_tokens`` is set; ignored otherwise.

    Returns:
        :class:`IngestionResult` summarizing the run.

    Raises:
        FileNotFoundError: ``input_path`` does not exist.
        ValueError: invalid chunking parameters or ``chunk_tokens`` set
            without a ``tokenizer``.
        ImportError: optional extras not installed for the format being ingested.
    """
    src = Path(input_path).expanduser().resolve()
    dst = Path(output_path).expanduser().resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)

    chunk_size_explicit = chunk_size is not None
    effective_chunk_size = chunk_size if chunk_size_explicit else DEFAULT_CHUNK_SIZE

    if pii_mask:
        # Lazy import: PII helpers live in data_audit.py; we don't want to
        # pay the audit module's import cost when masking is off.
        from .data_audit import mask_pii as _mask_pii

        mask_pii_fn: Optional[Callable[..., Any]] = _mask_pii
    else:
        mask_pii_fn = None

    tokenizer_obj: Any = None
    if chunk_tokens is not None:
        if not tokenizer:
            raise ValueError(
                "--chunk-tokens requires --tokenizer MODEL_NAME so the audit can size chunks against the right vocab."
            )
        if chunk_size_explicit:
            logger.warning(
                "Token-aware mode active (--chunk-tokens=%d): --chunk-size=%d is ignored.",
                chunk_tokens,
                effective_chunk_size,
            )
        tokenizer_obj = _load_tokenizer(tokenizer)
    if strategy == "paragraph" and overlap_tokens > 0:
        # Paragraph mode is intentionally non-overlapping (paragraphs are
        # the unit of indivisibility). Surfacing this as a one-line note
        # keeps the operator from silently losing their --overlap-tokens.
        logger.info(
            "--overlap-tokens=%d is ignored for strategy='paragraph' "
            "(paragraph chunks don't overlap by design). Use --strategy sliding for token-overlap.",
            overlap_tokens,
        )

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
    pdf_dedup_state: Dict[str, int] = {}

    # newline="\n" pins LF on Windows. JSONL Files spec requires LF, and
    # piping through tooling (jq -c, wc -l, downstream HF dataset loaders)
    # avoids CRLF surprises. Linux/macOS default is already LF.
    with open(dst, "w", encoding=encoding, newline="\n") as out_fh:
        for fpath in files:
            outcome = _process_one_file(
                fpath,
                out_fh,
                strategy=strategy,
                chunk_size=effective_chunk_size,
                overlap=overlap,
                mask_pii=mask_pii_fn,
                chunk_tokens=chunk_tokens,
                overlap_tokens=overlap_tokens,
                tokenizer=tokenizer_obj,
                pdf_dedup_state=pdf_dedup_state,
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
    pdf_lines_stripped = pdf_dedup_state.get("lines_stripped", 0)
    if pdf_lines_stripped:
        notes.append(
            f"PDF header/footer dedup stripped {pdf_lines_stripped} repeated line(s) "
            "(reduces audit near-duplicate noise)."
        )

    structured_notes: Dict[str, Any] = {
        "files_processed": files_processed,
        "files_skipped": files_skipped,
        "chunk_count": chunk_count,
        "total_chars": total_chars,
        "strategy": strategy,
        "format_counts": dict(format_counts),
        "pii_redaction_counts": dict(pii_redaction_counts),
    }
    if pdf_lines_stripped:
        structured_notes["pdf_header_footer_lines_stripped"] = pdf_lines_stripped
    if chunk_tokens is not None:
        structured_notes["chunk_tokens"] = chunk_tokens
        structured_notes["tokenizer"] = tokenizer

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
        notes_structured=structured_notes,
        pdf_header_footer_lines_stripped=pdf_lines_stripped,
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
    lines.append(f"Next: forgelm audit {result.output_path} --output ./audit/")
    lines.append(
        f"Or train: forgelm --config <your.yaml>  (set data.dataset_name_or_path: {os.fspath(result.output_path)})"
    )
    return "\n".join(lines)
