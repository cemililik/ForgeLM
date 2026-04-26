"""Dataset quality and governance audit — feeds EU AI Act Article 10 reporting.

Phase 11 (Data Audit) — analyzes a JSONL dataset and produces a
``data_audit_report.json`` covering:

* Sample count per split + column schema
* Text length distribution (min / max / mean / p50 / p95)
* Top-3 language detection (best-effort; ``langdetect`` optional)
* Near-duplicate rate via 64-bit simhash + Hamming distance
* Cross-split overlap (train ↔ validation ↔ test) — guards against
  silent train-test leakage that destroys benchmark fidelity
* Null / empty rate per text-bearing column
* PII flag counts via regex (emails, phones, credit cards, IBAN,
  national IDs for TR / DE / FR / US-SSN)

The same PII helpers (``detect_pii`` / ``mask_pii``) are reused by
``forgelm.ingestion`` for the optional ``--pii-mask`` flag.

Public API:

* :class:`AuditReport` — outcome dataclass
* :func:`audit_dataset` — the workhorse
* :func:`detect_pii` / :func:`mask_pii` — string-level helpers
* :func:`compute_simhash` — exposed for testing
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("forgelm.data_audit")


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


PII_TYPES: Tuple[str, ...] = ("email", "phone", "credit_card", "iban", "tr_id", "de_id", "fr_ssn", "us_ssn")


# Columns we treat as text payloads when computing length / language / dedup.
# Order matters: first match wins per row.
_TEXT_COLUMNS: Tuple[str, ...] = ("text", "content", "completion", "prompt")


# Default Hamming-distance threshold for "near-duplicate" via 64-bit simhash.
# 3 bits ≈ ~95% similarity at 64-bit width — same threshold the simhash paper
# uses for the canonical web-page-dedup deployment.
DEFAULT_NEAR_DUP_HAMMING: int = 3


@dataclass
class AuditReport:
    """Structured audit outcome — JSON-serializable via :func:`asdict`.

    Both :attr:`source_path` (absolute, for traceability) and
    :attr:`source_input` (the literal string the operator passed in) are
    captured: absolute paths are useful for forensic correlation but
    leak the auditor's local filesystem layout, so consumers that need
    portability across machines should prefer :attr:`source_input`.
    """

    generated_at: str
    source_path: str
    source_input: str
    total_samples: int
    splits: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    cross_split_overlap: Dict[str, Any] = field(default_factory=dict)
    pii_summary: Dict[str, int] = field(default_factory=dict)
    near_duplicate_summary: Dict[str, Any] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# PII regex — module level so they're compiled once
# ---------------------------------------------------------------------------


# Pattern dict iteration order = scan / mask precedence. Keep most specific
# patterns first so a span that could match two categories is attributed to
# the narrower one (e.g. an SSN is also a digit run; we want it flagged as
# us_ssn, not as phone). When the same span matches multiple patterns during
# masking, the FIRST pattern in this dict wins and the span is replaced
# before the next pattern sees it — that's the documented "first match wins"
# semantics referenced in :func:`mask_pii`.
_PII_PATTERNS: Dict[str, re.Pattern] = {
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "iban": re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b"),
    # Credit cards captured first within the digit-run categories, then
    # Luhn-validated (see _is_credit_card). Greedy ``*`` instead of ``*?``:
    # both match the same set of strings here (``\b`` end-anchor forces a
    # full match) but the greedy form avoids unnecessary engine backtracking.
    "credit_card": re.compile(r"\b(?:\d[ -]*){13,19}\b"),
    "us_ssn": re.compile(r"\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b"),
    "fr_ssn": re.compile(r"\b[12]\d{2}(0[1-9]|1[0-2])(2[AB]|\d{2})\d{3}\d{3}(\d{2})?\b"),
    "tr_id": re.compile(r"\b\d{11}\b"),  # TR national ID is 11 digits, see _is_tr_id
    # German Personalausweis serial: leading letter, then 7-8 digits, then
    # optional alphanumeric check char. Tighter than the previous
    # ``[A-Z0-9]{9,10}`` which collided with IATA codes / UUID fragments /
    # API-key fragments.
    "de_id": re.compile(r"\b[A-Z]\d{7,8}[A-Z0-9]?\b"),
    # Phone numbers — the noisiest pattern in production. Anchored to either
    # an international prefix ('+') or a parenthesized area code so that
    # bare digit runs (timestamps, log line numbers, ISO dates, ID codes)
    # don't trip false positives. Use ingestion --pii-mask to redact at write
    # time; keep audit's recall slightly lower than the other categories to
    # avoid audit fatigue.
    "phone": re.compile(
        r"(?<!\w)"
        r"(?:"
        r"\+\d{1,3}[\s.-]?\d{2,4}[\s.-]?\d{2,4}[\s.-]?\d{0,4}"  # +CC area#-#-#
        r"|"
        r"\(\d{2,4}\)[\s.-]?\d{2,4}[\s.-]?\d{2,4}"  # (area) #-#
        r")"
        r"(?!\w)"
    ),
}


def _is_credit_card(candidate: str) -> bool:
    digits = [int(c) for c in candidate if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    # Luhn check.
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _is_tr_id(candidate: str) -> bool:
    """Validate TR national ID (TC Kimlik No) by its checksum rules."""
    if len(candidate) != 11 or not candidate.isdigit():
        return False
    digits = [int(c) for c in candidate]
    if digits[0] == 0:
        return False
    odd_sum = digits[0] + digits[2] + digits[4] + digits[6] + digits[8]
    even_sum = digits[1] + digits[3] + digits[5] + digits[7]
    if (odd_sum * 7 - even_sum) % 10 != digits[9]:
        return False
    return sum(digits[:10]) % 10 == digits[10]


def _validate_match(pii_type: str, match: str) -> bool:
    if pii_type == "credit_card":
        return _is_credit_card(match)
    if pii_type == "tr_id":
        return _is_tr_id(match)
    return True


def detect_pii(text: Any) -> Dict[str, int]:
    """Return a ``{pii_type: count}`` map for the given string.

    The signature is intentionally ``Any`` — the audit calls this with
    arbitrary JSONL row payloads and we explicitly want a defensive empty
    return for ``None`` / numbers / lists rather than a TypeError. String
    callers see no behavioural difference; static-checker friction goes
    away.

    Validation: credit cards run through Luhn; TR national IDs run through
    the TC Kimlik No checksum. Other categories use regex shape only — false
    positives are intentional (the audit is meant to over-report and let the
    operator decide).
    """
    counts: Dict[str, int] = {}
    if not text or not isinstance(text, str):
        return counts
    for pii_type, pattern in _PII_PATTERNS.items():
        for match in pattern.findall(text):
            payload = match if isinstance(match, str) else " ".join(p for p in match if p)
            if not payload:
                continue
            if not _validate_match(pii_type, payload):
                continue
            counts[pii_type] = counts.get(pii_type, 0) + 1
    return counts


def mask_pii(
    text: Any,
    replacement: str = "[REDACTED]",
    *,
    return_counts: bool = False,
) -> Any:
    """Return ``text`` with every detected PII span replaced by ``replacement``.

    Like :func:`detect_pii`, the input type is ``Any`` so callers passing
    arbitrary JSONL payloads get a defensive passthrough on non-strings
    rather than a TypeError. ``None`` returns ``None``; ints / lists / etc.
    are returned unchanged.

    Pattern precedence is the dict order in :data:`_PII_PATTERNS` — most
    specific patterns first (email, IBAN, credit card, national IDs) so a
    span that would match multiple categories is attributed to the narrower
    one. Phone is scanned LAST and is anchored to ``+CC`` or ``(area)``
    formats so bare digit runs (timestamps, IDs, dates) do not collide.

    Args:
        text: Input string. Non-string values are returned unchanged.
        replacement: String to substitute in for each detected span.
        return_counts: When True, return ``(masked_text, counts_dict)`` where
            ``counts_dict[pii_type]`` is the number of spans actually replaced
            by THIS pattern in this call. Multi-pattern overlap is reported
            only once per span (the first / most specific pattern wins, the
            same way mask_pii rewrites the text). Default ``False`` keeps
            backwards compat for the 1-arg form.
    """
    if not text or not isinstance(text, str):
        return (text, {}) if return_counts else text
    counts: Dict[str, int] = {}
    out = text
    for pii_type, pattern in _PII_PATTERNS.items():

        def _replace(match: re.Match, _t: str = pii_type) -> str:
            if _validate_match(_t, match.group(0)):
                counts[_t] = counts.get(_t, 0) + 1
                return replacement
            return match.group(0)

        out = pattern.sub(_replace, out)
    return (out, counts) if return_counts else out


# ---------------------------------------------------------------------------
# Simhash + near-duplicate detection
# ---------------------------------------------------------------------------


_TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)


def _tokenize(text: str) -> List[str]:
    return [tok.lower() for tok in _TOKEN_PATTERN.findall(text or "")]


def compute_simhash(text: str, *, bits: int = 64) -> int:
    """64-bit simhash over case-folded word tokens.

    Uses BLAKE2b (non-cryptographic use — pure bit-mixing) with a truncated
    digest, then per-bit majority voting weighted by token frequency to
    produce the final fingerprint. BLAKE2b is on the modern allowlist
    (vs. flagged MD5/SHA1) and natively supports digest_size truncation,
    avoiding the slice we'd need with SHA-256. Empty input → ``0``.
    """
    tokens = _tokenize(text)
    if not tokens:
        return 0

    weights: Dict[str, int] = {}
    for token in tokens:
        weights[token] = weights.get(token, 0) + 1

    digest_bytes = bits // 8
    bit_scores = [0] * bits
    for token, weight in weights.items():
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=digest_bytes).digest()
        token_hash = int.from_bytes(digest, "big")
        for i in range(bits):
            bit = (token_hash >> i) & 1
            bit_scores[i] += weight if bit else -weight

    fingerprint = 0
    for i, score in enumerate(bit_scores):
        if score > 0:
            fingerprint |= 1 << i
    return fingerprint


def hamming_distance(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def find_near_duplicates(
    fingerprints: List[int],
    *,
    threshold: int = DEFAULT_NEAR_DUP_HAMMING,
) -> List[Tuple[int, int, int]]:
    """Pair-find rows whose simhash Hamming distance ≤ ``threshold``.

    Returns ``[(i, j, distance), ...]`` with ``i < j``. Quadratic in the
    number of fingerprints; intended for audit-time use on datasets up to
    ~50 K rows. For larger datasets, an LSH band index would be required —
    out of scope for v0.5.0.
    """
    pairs: List[Tuple[int, int, int]] = []
    for i, fp_i in enumerate(fingerprints):
        if fp_i == 0:
            continue
        for j in range(i + 1, len(fingerprints)):
            fp_j = fingerprints[j]
            if fp_j == 0:
                continue
            distance = hamming_distance(fp_i, fp_j)
            if distance <= threshold:
                pairs.append((i, j, distance))
    return pairs


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _detect_language(text: str) -> str:
    if not text or len(text) < 20:
        return "unknown"
    try:
        from langdetect import DetectorFactory, detect

        DetectorFactory.seed = 0
        return detect(text)
    except ImportError:
        return "unknown (install forgelm[ingestion])"
    except Exception:
        return "unknown"


def _length_stats(lengths: List[int]) -> Dict[str, float]:
    if not lengths:
        return {}
    sorted_lens = sorted(lengths)
    n = len(sorted_lens)
    return {
        "min": sorted_lens[0],
        "max": sorted_lens[-1],
        "mean": round(sum(sorted_lens) / n, 1),
        "p50": sorted_lens[n // 2],
        "p95": sorted_lens[min(n - 1, int(n * 0.95))],
    }


def _extract_text_payload(row: Dict[str, Any]) -> str:
    """Pick the most plausible text column from a row for stats / dedup."""
    for col in _TEXT_COLUMNS:
        val = row.get(col)
        if isinstance(val, str) and val.strip():
            return val
    # ``messages`` / chat schemas: concatenate role-tagged content.
    msgs = row.get("messages")
    if isinstance(msgs, list):
        parts = []
        for m in msgs:
            if isinstance(m, dict) and isinstance(m.get("content"), str):
                parts.append(m["content"])
        if parts:
            return "\n".join(parts)
    return ""


def _read_jsonl_split(path: Path) -> Tuple[List[Any], int, int]:
    """Read a JSONL split tolerantly. Returns ``(rows, parse_errors, decode_errors)``.

    * UTF-8 decode is permissive (``errors="replace"``) — a single mojibake
      line never aborts the whole audit. Lines containing the U+FFFD
      replacement char are tracked separately so the operator gets a
      structured signal.
    * ``json.JSONDecodeError`` is caught per line; the parser-error count
      is returned for the audit report so silently dropping rows leaves a
      paper trail.
    * Returned ``rows`` may contain non-dict JSON (lists, scalars). The
      auditor downstream knows to handle them — :func:`_extract_text_payload`
      and :func:`_audit_split` both already guard ``isinstance(row, dict)``.
    """
    rows: List[Any] = []
    parse_errors = 0
    decode_errors = 0
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line_number, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            if "�" in line:
                decode_errors += 1
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                parse_errors += 1
                logger.warning("Skipping malformed JSONL line %d in %s: %s", line_number, path, exc)
    return rows, parse_errors, decode_errors


_PROGRESS_INTERVAL: int = 5000
"""Emit a progress log every N rows when a split is large enough that the
audit's silent stretch is over a few seconds. Threshold picked so smoke
tests / quickstart audits stay quiet but real corpora surface signal."""


def _compute_schema(rows: List[Any]) -> Tuple[List[str], List[str], int]:
    """Inspect rows; return (column_union, drift_columns, non_object_rows).

    ``base_columns`` for drift is the **modal keyset** (most common shape
    across rows). Picking rows[0] would falsely flag every other column
    when row 0 is the outlier (header row, missing optional field,
    non-dict junk).
    """
    seen_columns: Dict[str, None] = {}  # ordered set
    keysets: List[frozenset] = []
    non_object_rows = 0
    for row in rows:
        if isinstance(row, dict):
            keys = frozenset(row.keys())
            keysets.append(keys)
            for col in keys:
                seen_columns.setdefault(col, None)
        else:
            non_object_rows += 1
    if keysets:
        most_common_keyset, _ = Counter(keysets).most_common(1)[0]
        base_columns = set(most_common_keyset)
    else:
        base_columns = set()
    drift_columns = [c for c in seen_columns if c not in base_columns]
    return list(seen_columns), drift_columns, non_object_rows


def _compute_payloads(rows: List[Any]) -> Tuple[List[str], int]:
    """Extract text-payload-or-empty for each row; return (payloads, null_or_empty_count).

    Non-dict rows are silently treated as empty here — :func:`_compute_schema`
    already exposed them under ``non_object_rows``.
    """
    payloads: List[str] = []
    null_or_empty = 0
    for row in rows:
        if not isinstance(row, dict):
            null_or_empty += 1
            payloads.append("")
            continue
        payload = _extract_text_payload(row)
        if not payload:
            null_or_empty += 1
        payloads.append(payload)
    return payloads, null_or_empty


def _compute_top_languages(payloads: List[str], sample_size: int = 200) -> List[Dict[str, Any]]:
    """Top-3 languages by count, sampled to bound cost on large splits."""
    sample = payloads[: min(sample_size, len(payloads))]
    counts: Dict[str, int] = {}
    for t in sample:
        lang = _detect_language(t)
        if lang:
            counts[lang] = counts.get(lang, 0) + 1
    if not counts:
        return []
    top3 = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:3]
    return [{"code": code, "count": n} for code, n in top3]


def _compute_fingerprints(split_name: str, payloads: List[str]) -> List[int]:
    """Per-row simhash with operator-friendly progress logging on large splits."""
    n_rows = len(payloads)
    log_progress = n_rows >= _PROGRESS_INTERVAL
    if log_progress:
        logger.info("audit/%s: computing simhashes for %d rows…", split_name, n_rows)
    fingerprints: List[int] = []
    for idx, t in enumerate(payloads):
        fingerprints.append(compute_simhash(t))
        if log_progress and (idx + 1) % _PROGRESS_INTERVAL == 0:
            logger.info("audit/%s: %d / %d rows fingerprinted", split_name, idx + 1, n_rows)
    return fingerprints


def _aggregate_pii(payloads: List[str]) -> Dict[str, int]:
    """Sum :func:`detect_pii` flags across all payloads."""
    counts: Dict[str, int] = {}
    for t in payloads:
        for kind, n in detect_pii(t).items():
            counts[kind] = counts.get(kind, 0) + n
    return counts


def _audit_split(
    split_name: str,
    rows: List[Any],
    *,
    near_dup_threshold: int = DEFAULT_NEAR_DUP_HAMMING,
) -> Tuple[Dict[str, Any], List[int], Dict[str, int]]:
    """Per-split metrics. Returns (info_dict, simhashes_list, pii_counts_dict).

    Tolerates non-dict rows (raw arrays, scalars, etc. — anything well-formed
    JSON but not an object). They are surfaced as ``non_object_rows`` so the
    operator distinguishes "row dropped because it was the wrong shape" from
    "row had an empty text payload". The function is a thin orchestrator over
    the per-pass helpers above; each helper owns one concern and is unit-
    testable in isolation.
    """
    info: Dict[str, Any] = {"sample_count": len(rows)}
    if not rows:
        info["near_duplicate_pairs"] = 0
        return info, [], {}

    columns, drift_columns, non_object_rows = _compute_schema(rows)
    info["columns"] = columns
    if drift_columns:
        info["schema_drift_columns"] = drift_columns
    if non_object_rows:
        info["non_object_rows"] = non_object_rows

    payloads, null_or_empty = _compute_payloads(rows)
    info["text_length"] = _length_stats([len(t) for t in payloads if t])
    info["null_or_empty_count"] = null_or_empty
    info["null_or_empty_rate"] = round(null_or_empty / len(rows), 4)

    languages_top3 = _compute_top_languages(payloads)
    if languages_top3:
        info["languages_top3"] = languages_top3

    fingerprints = _compute_fingerprints(split_name, payloads)
    info["simhash_distinct"] = len({fp for fp in fingerprints if fp != 0})

    pii_counts_split = _aggregate_pii(payloads)
    if pii_counts_split:
        info["pii_counts"] = pii_counts_split

    # Within-split near-duplicate detection lives here so info[] is fully
    # owned by _audit_split; the orchestrator never back-fills its fields.
    if len(rows) >= _PROGRESS_INTERVAL:
        logger.info("audit/%s: scanning for near-duplicates (O(n²); %d rows)…", split_name, len(rows))
    within_pairs = find_near_duplicates(fingerprints, threshold=near_dup_threshold)
    info["near_duplicate_pairs"] = len(within_pairs)

    return info, fingerprints, pii_counts_split


def _count_leaked_rows(source: List[int], target: List[int], threshold: int) -> int:
    """Rows in ``source`` whose nearest neighbour in ``target`` is within ``threshold``."""
    return sum(1 for fp in source if any(hamming_distance(fp, other) <= threshold for other in target))


def _pair_leak_payload(
    a: str,
    fp_a: List[int],
    b: str,
    fp_b: List[int],
    threshold: int,
) -> Dict[str, Any]:
    """Both-directional leak counts + rates for one (a, b) split pair."""
    leaked_in_a = _count_leaked_rows(fp_a, fp_b, threshold)
    leaked_in_b = _count_leaked_rows(fp_b, fp_a, threshold)
    return {
        f"leaked_rows_in_{a}": leaked_in_a,
        f"leak_rate_{a}": round(leaked_in_a / len(fp_a), 4),
        f"leaked_rows_in_{b}": leaked_in_b,
        f"leak_rate_{b}": round(leaked_in_b / len(fp_b), 4),
    }


def _cross_split_overlap(
    fingerprints_by_split: Dict[str, List[int]],
    threshold: int,
) -> Dict[str, Any]:
    """Pairwise leakage report across train/validation/test splits.

    Reports leak rate **in both directions** — the symmetric ratio
    (shared / smaller-split-size) is the metric that actually destroys
    benchmark fidelity, but the asymmetric one (shared / larger split)
    is informative too. Without both, an operator scanning
    ``train__test = 0.05`` could miss that the same 5 rows leak 50% of
    a small test set.
    """
    nonzero = {name: [fp for fp in fps if fp != 0] for name, fps in fingerprints_by_split.items()}
    splits = list(nonzero.keys())
    report: Dict[str, Any] = {"hamming_threshold": threshold, "pairs": {}}
    for i, a in enumerate(splits):
        fp_a = nonzero[a]
        if not fp_a:
            continue
        for j in range(i + 1, len(splits)):
            b = splits[j]
            fp_b = nonzero[b]
            if not fp_b:
                continue
            report["pairs"][f"{a}__{b}"] = _pair_leak_payload(a, fp_a, b, fp_b, threshold)
    return report


# Common synonyms for the canonical split names. Folded onto canonical at
# load time so leakage analysis treats e.g. ``dev.jsonl`` and
# ``validation.jsonl`` as the same split semantically. Alias preference is
# intentional: a directory containing both ``validation.jsonl`` and
# ``dev.jsonl`` should warn (loud) rather than silently merge.
_SPLIT_ALIASES: Dict[str, str] = {
    "train": "train",
    "validation": "validation",
    "valid": "validation",
    "val": "validation",
    "dev": "validation",
    "test": "test",
    "eval": "test",
    "holdout": "test",
}


def _scan_canonical_split_files(src: Path) -> Tuple[Dict[str, Path], List[str]]:
    """Discover ``train`` / ``validation`` / ``test`` files via canonical names + aliases."""
    layouts: Dict[str, Path] = {}
    notes: List[str] = []
    for stem, canonical in _SPLIT_ALIASES.items():
        candidate = src / f"{stem}.jsonl"
        if not candidate.is_file():
            continue
        if canonical in layouts:
            notes.append(
                f"both '{layouts[canonical].name}' and '{candidate.name}' map to "
                f"the '{canonical}' split; using the first one. Rename to disambiguate."
            )
            continue
        if stem != canonical:
            notes.append(f"'{candidate.name}' treated as the '{canonical}' split.")
        layouts[canonical] = candidate
    return layouts, notes


def _scan_pseudo_split_files(src: Path) -> Tuple[Dict[str, Path], List[str]]:
    """Last-resort fallback: every ``*.jsonl`` becomes its own pseudo-split.

    Cross-split leakage analysis on pseudo-splits is meaningless (those
    files probably aren't a real train/test partition), so warn loudly.
    """
    layouts: Dict[str, Path] = {}
    notes: List[str] = []
    for jsonl in sorted(src.glob("*.jsonl")):
        layouts[jsonl.stem] = jsonl
    if layouts:
        msg = (
            f"no canonical split files found in '{src}'. "
            "Each .jsonl is being audited as its own pseudo-split — "
            "cross-split leakage analysis is meaningless without a real partition."
        )
        notes.append(msg)
        logger.warning(msg)
    return layouts, notes


def _resolve_directory_splits(src: Path) -> Tuple[Dict[str, Path], List[str]]:
    """Find a usable split layout under ``src`` (canonical first, pseudo as fallback)."""
    layouts, notes = _scan_canonical_split_files(src)
    if layouts:
        return layouts, notes
    return _scan_pseudo_split_files(src)


def _resolve_input(source: str) -> Tuple[Dict[str, Path], List[str]]:
    """Map the user-supplied path to a ``{split_name: path}`` dict + notes.

    Two layouts are supported:
    * Single ``.jsonl`` file → treated as the ``train`` split.
    * Directory with files matching canonical names (``train.jsonl`` /
      ``validation.jsonl`` / ``test.jsonl``) or common aliases (``dev`` /
      ``val`` / ``valid`` / ``eval`` / ``holdout``).
    """
    src = Path(source).expanduser().resolve()
    if src.is_file():
        return {"train": src}, []
    if src.is_dir():
        layouts, notes = _resolve_directory_splits(src)
        if layouts:
            return layouts, notes
    raise FileNotFoundError(
        f"Audit input not found or empty: '{src}'. "
        f"Pass a .jsonl file or a directory containing train.jsonl / validation.jsonl / test.jsonl."
    )


# ---------------------------------------------------------------------------
# Per-split processing — extracted from audit_dataset for readability and
# testability. Each helper owns one concern; the orchestrator stitches them.
# ---------------------------------------------------------------------------


@dataclass
class _SplitOutcome:
    """Bundle of per-split results assembled by :func:`_process_split`."""

    info: Dict[str, Any]
    fingerprints: List[int]
    pii_split: Dict[str, int]
    row_count: int
    parse_errors: int
    decode_errors: int
    split_notes: List[str]


def _process_split(
    split_name: str,
    path: Path,
    *,
    near_dup_threshold: int,
) -> _SplitOutcome:
    """Read + audit one split. Tolerates per-split filesystem failures."""
    try:
        rows, parse_errors, decode_errors = _read_jsonl_split(path)
    except OSError as exc:
        logger.warning("Could not read split '%s' (%s): %s — skipping.", split_name, path, exc)
        return _SplitOutcome(
            info={"error": f"read_failed: {exc}", "path": str(path)},
            fingerprints=[],
            pii_split={},
            row_count=0,
            parse_errors=0,
            decode_errors=0,
            split_notes=[f"split '{split_name}' skipped (read failure: {exc})"],
        )

    logger.info("audit: scanning split '%s' (%d rows from %s)", split_name, len(rows), path.name)
    info, fingerprints, pii_split = _audit_split(split_name, rows, near_dup_threshold=near_dup_threshold)

    split_notes: List[str] = []
    # Surface JSONL hygiene metrics on the split itself so the report
    # distinguishes "this split has 1240 rows" from "this split had 1330
    # lines but 90 were malformed JSON we silently dropped".
    if parse_errors:
        info["parse_errors"] = parse_errors
        split_notes.append(
            f"split '{split_name}': {parse_errors} malformed JSONL line(s) "
            "skipped — metrics computed over the parseable subset only."
        )
    if decode_errors:
        info["decode_errors"] = decode_errors
        split_notes.append(
            f"split '{split_name}': {decode_errors} line(s) had non-UTF-8 "
            "bytes (replaced with U+FFFD). Re-encode the source file as "
            "UTF-8 if these rows matter."
        )

    return _SplitOutcome(
        info=info,
        fingerprints=fingerprints,
        pii_split=pii_split,
        row_count=len(rows),
        parse_errors=parse_errors,
        decode_errors=decode_errors,
        split_notes=split_notes,
    )


def _pii_summary_notes(pii_summary: Dict[str, int]) -> List[str]:
    """Operator-actionable note (or "none flagged") for the aggregate PII counts."""
    if not pii_summary:
        return ["No PII flagged. (Regex-based detector — false negatives possible.)"]
    flag_total = sum(pii_summary.values())
    breakdown = ", ".join(f"{k}={v}" for k, v in sorted(pii_summary.items()))
    return [
        f"PII flags surfaced ({flag_total} total: {breakdown}). "
        "Review before publishing; mask with `forgelm ingest --pii-mask` "
        "or use `forgelm.data_audit.mask_pii` programmatically."
    ]


def _cross_split_leak_notes(cross: Dict[str, Any]) -> List[str]:
    """Surface the WORST leak direction so an asymmetric figure doesn't bury it."""
    cross_pairs = cross.get("pairs", {}) or {}
    leaking = []
    for name, payload in cross_pairs.items():
        rates = [v for k, v in payload.items() if k.startswith("leak_rate_")]
        if rates and max(rates) > 0:
            leaking.append((name, max(rates)))
    if not leaking:
        return []
    worst = max(leaking, key=lambda kv: kv[1])
    return [
        f"Cross-split leakage detected in {len(leaking)} pair(s): "
        f"{', '.join(name for name, _ in leaking)}. "
        f"Worst leak rate: {worst[1]:.2%} ({worst[0]}). "
        "Re-shuffle splits before benchmarking — leaked rows poison test fidelity."
    ]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def audit_dataset(
    source: str,
    *,
    output_dir: Optional[str] = None,
    near_dup_threshold: int = DEFAULT_NEAR_DUP_HAMMING,
) -> AuditReport:
    """Run the audit pipeline over a JSONL file or split-keyed directory.

    Args:
        source: Path to a ``.jsonl`` file (single split) or a directory
            containing ``train.jsonl`` / ``validation.jsonl`` / ``test.jsonl``.
        output_dir: When set, writes ``data_audit_report.json`` under this
            directory (created if missing). Returned :class:`AuditReport`
            is identical either way.
        near_dup_threshold: Hamming distance cutoff for the simhash-based
            near-duplicate detector. Default 3 (≈95% similarity).

    Returns:
        :class:`AuditReport`. JSON-serialize via ``asdict(report)``.
    """
    splits_paths, resolution_notes = _resolve_input(source)

    splits_info: Dict[str, Dict[str, Any]] = {}
    fingerprints_by_split: Dict[str, List[int]] = {}
    pii_summary: Dict[str, int] = {}
    total_samples = 0
    near_dup_pairs: Dict[str, int] = {}
    notes: List[str] = list(resolution_notes)

    parse_errors_total = 0
    decode_errors_total = 0

    for split_name, path in splits_paths.items():
        outcome = _process_split(split_name, path, near_dup_threshold=near_dup_threshold)
        splits_info[split_name] = outcome.info
        fingerprints_by_split[split_name] = outcome.fingerprints
        total_samples += outcome.row_count
        near_dup_pairs[split_name] = outcome.info.get("near_duplicate_pairs", 0)
        notes.extend(outcome.split_notes)
        parse_errors_total += outcome.parse_errors
        decode_errors_total += outcome.decode_errors
        for kind, count in outcome.pii_split.items():
            pii_summary[kind] = pii_summary.get(kind, 0) + count

    cross = _cross_split_overlap(fingerprints_by_split, near_dup_threshold)
    notes.extend(_pii_summary_notes(pii_summary))
    notes.extend(_cross_split_leak_notes(cross))

    near_dup_total = sum(near_dup_pairs.values())
    if near_dup_total > 0:
        notes.append(
            f"{near_dup_total} near-duplicate pair(s) found within splits. "
            "Inspect; identical chunks waste training compute and can overweight specific phrasing."
        )

    if parse_errors_total or decode_errors_total:
        notes.append(
            f"Data integrity: {parse_errors_total} parse error(s) + "
            f"{decode_errors_total} decode error(s) across all splits. "
            "These rows did NOT contribute to per-split metrics — re-emit the "
            "JSONL after fixing or accept the parseable subset as audited."
        )

    report = AuditReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        source_path=os.fspath(Path(source).expanduser().resolve()),
        source_input=source,
        total_samples=total_samples,
        splits=splits_info,
        cross_split_overlap=cross,
        pii_summary=pii_summary,
        near_duplicate_summary={
            "hamming_threshold": near_dup_threshold,
            "pairs_per_split": near_dup_pairs,
        },
        notes=notes,
    )

    if output_dir:
        out_dir = Path(output_dir).expanduser().resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "data_audit_report.json"
        # newline="\n" pins LF on Windows so byte-exact reproducibility
        # checksums match Linux/macOS runs (the JSONL Files spec also
        # requires LF terminators).
        with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(asdict(report), fh, indent=2, ensure_ascii=False)
        logger.info("Wrote audit report: %s", out_path)

    return report


def summarize_report(report: AuditReport) -> str:
    """Render an :class:`AuditReport` as a multi-line operator-facing summary."""
    lines = [
        "Data audit summary",
        f"  Source        : {report.source_path}",
        f"  Total samples : {report.total_samples}",
        f"  Splits        : {', '.join(report.splits)}",
    ]
    for split_name, info in report.splits.items():
        lines.append(f"  └─ {split_name}: n={info.get('sample_count', 0)}")
        text_len = info.get("text_length") or {}
        if text_len:
            lines.append(
                f"     length  min={text_len['min']} max={text_len['max']} mean={text_len['mean']} p95={text_len['p95']}"
            )
        if info.get("null_or_empty_count"):
            lines.append(f"     null/empty: {info['null_or_empty_count']} ({info['null_or_empty_rate'] * 100:.1f}%)")
        if info.get("near_duplicate_pairs"):
            lines.append(f"     near-duplicate pairs: {info['near_duplicate_pairs']}")
        if info.get("languages_top3"):
            tops = ", ".join(f"{e['code']}={e['count']}" for e in info["languages_top3"])
            lines.append(f"     languages (top-3): {tops}")
        if info.get("pii_counts"):
            pii = ", ".join(f"{k}={v}" for k, v in sorted(info["pii_counts"].items()))
            lines.append(f"     PII             : {pii}")

    if report.cross_split_overlap.get("pairs"):
        lines.append("  Cross-split leakage:")
        for pair_name, payload in report.cross_split_overlap["pairs"].items():
            lines.append(f"    {pair_name}: {payload}")
    return "\n".join(lines)
