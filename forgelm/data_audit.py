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
import tempfile
from collections import Counter, OrderedDict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

logger = logging.getLogger("forgelm.data_audit")


# Phase 11.5: optional xxhash backend for the simhash digest. xxh3_64 is a
# non-cryptographic 64-bit hash that is materially faster (typically 4-10×)
# than ``hashlib.blake2b`` on short string keys — meaningful for audits that
# fingerprint millions of tokens. We fall back to BLAKE2b when the dependency
# is not present so the audit module still works against a bare install.
try:  # pragma: no cover — exercised by the dedicated extras-skip tests
    import xxhash as _xxhash

    _HAS_XXHASH = True
except ImportError:  # pragma: no cover
    _xxhash = None
    _HAS_XXHASH = False


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


PII_TYPES: Tuple[str, ...] = ("email", "phone", "credit_card", "iban", "tr_id", "de_id", "fr_ssn", "us_ssn")


# Phase 11.5: PII severity grading. A flat ``{type: count}`` map gives zero
# guidance to a compliance reviewer staring at the audit JSON — they have to
# remember by hand that ``credit_card`` is materially worse than ``phone``.
# The tiers below encode the consensus regulatory weighting (PCI-DSS for
# financial; GDPR Art. 9 + ENISA for identifiers) so the audit surfaces a
# one-glance verdict via :data:`PII_SEVERITY`. Tweak the table when local
# law disagrees — the audit honours whatever map is loaded at call time.
PII_SEVERITY: Dict[str, str] = {
    # Financial / fully reversible identity theft → highest weight.
    "credit_card": "critical",
    "iban": "critical",
    # Government-issued identifiers → high. Tied to a specific person and
    # often re-used across systems; leakage is materially harder to undo
    # than a phone or email.
    "tr_id": "high",
    "de_id": "high",
    "fr_ssn": "high",
    "us_ssn": "high",
    # Direct contact identifiers → medium. Routinely collected, but
    # leakage enables phishing / social engineering at scale.
    "email": "medium",
    # Phone numbers → low. Anchored regex (see ``_PII_PATTERNS``) keeps
    # recall conservative; many spans are operational metadata that is
    # not actually personally identifying.
    "phone": "low",
}


PII_SEVERITY_ORDER: Tuple[str, ...] = ("critical", "high", "medium", "low")
"""Display order — most-severe first so the operator-facing summary leads
with the worst-case findings rather than burying them behind low tiers."""


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
    pii_severity: Dict[str, Any] = field(default_factory=dict)
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


# Phase 11.5: per-token digest cache. Token frequency follows Zipf's law —
# the top few thousand tokens (the / and / common stop-words / domain
# vocabulary) dominate hits across an entire corpus. Memoising the digest
# at this granularity collapses millions of hashes into ten thousand on a
# typical run. lru_cache is process-wide and bounded; ``maxsize=10_000``
# trades ~1-2 MB of cache for the throughput win.
@lru_cache(maxsize=10_000)
def _token_digest(token: str, bits: int = 64) -> int:
    """Hash one tokenised word into a ``bits``-wide integer.

    Backend selection (decided at import time):

    * **xxhash.xxh3_64** when the optional ``xxhash`` dependency is
      installed and ``bits == 64`` — non-cryptographic, several times
      faster than BLAKE2b on short strings.
    * **hashlib.blake2b** otherwise (and for non-64-bit widths, e.g. tests
      that pin a smaller fingerprint). BLAKE2b is on the modern allowlist
      and supports native ``digest_size`` truncation.

    The choice is deterministic per-process: a corpus audited with xxhash
    will produce different fingerprints than one audited with BLAKE2b, but
    near-duplicate decisions stay stable across runs of the same process.
    Operators that need cross-machine reproducibility should pin the
    presence/absence of ``xxhash`` in their environment.
    """
    encoded = token.encode("utf-8")
    if _HAS_XXHASH and bits == 64:
        return _xxhash.xxh3_64(encoded).intdigest()
    digest_bytes = bits // 8
    return int.from_bytes(
        hashlib.blake2b(encoded, digest_size=digest_bytes).digest(),
        "big",
    )


def compute_simhash(text: str, *, bits: int = 64) -> int:
    """64-bit simhash over case-folded word tokens.

    Per-bit majority voting weighted by token frequency, where each
    distinct token's hash is computed once via :func:`_token_digest`
    (cached at module scope). Empty input → ``0``.
    """
    tokens = _tokenize(text)
    if not tokens:
        return 0

    weights: Dict[str, int] = {}
    for token in tokens:
        weights[token] = weights.get(token, 0) + 1

    bit_scores = [0] * bits
    for token, weight in weights.items():
        token_hash = _token_digest(token, bits)
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


_LSH_MIN_BAND_BITS: int = 4
"""Minimum useful bits per LSH band. Below this the band's value space is
so narrow (≤ 16 buckets) that almost every row collides and the index
degrades to a brute-force scan with extra bookkeeping. We fall back to a
linear pair walk when adaptive banding can't reach this floor."""


def _band_count_for_threshold(threshold: int, bits: int) -> int:
    """Choose ``bands`` so that pigeonhole guarantees recall.

    With ``bands = threshold + 1`` and a ``bits``-wide fingerprint, two
    fingerprints differing in ``≤ threshold`` bits MUST agree on at least
    one full band (``threshold`` differing bits spread over ``threshold + 1``
    bands leaves at least one band intact). The caller is responsible for
    verifying the band-bit floor; we return 0 to signal "fall back to brute
    force" when the configured threshold leaves bands too narrow to be
    useful as a bucket key.
    """
    if threshold < 0:
        return 0
    bands = threshold + 1
    if bits // bands < _LSH_MIN_BAND_BITS:
        return 0
    return bands


def _split_into_bands(fingerprint: int, bands: int, bits: int) -> List[int]:
    """Slice ``fingerprint`` into ``bands`` equal-width band values.

    Lower bits land in band 0 to keep the slicing deterministic across
    fingerprint widths; the band index is part of the bucket key, so there
    is no security/avalanche concern.
    """
    band_bits = bits // bands
    mask = (1 << band_bits) - 1
    return [(fingerprint >> (i * band_bits)) & mask for i in range(bands)]


def _find_near_duplicates_brute(
    fingerprints: List[int],
    threshold: int,
) -> List[Tuple[int, int, int]]:
    """Quadratic fallback used when LSH banding can't be configured."""
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


def find_near_duplicates(
    fingerprints: List[int],
    *,
    threshold: int = DEFAULT_NEAR_DUP_HAMMING,
    bits: int = 64,
) -> List[Tuple[int, int, int]]:
    """Pair-find rows whose simhash Hamming distance ≤ ``threshold``.

    Returns ``[(i, j, distance), ...]`` with ``i < j``.

    Uses **LSH banding** to drop the typical case from ``O(n²)`` to
    roughly ``O(n × k)`` where ``k`` is the average bucket fan-out:

    1. Each fingerprint is sliced into ``threshold + 1`` equal-width bands.
       Pigeonhole guarantees that two fingerprints differing in at most
       ``threshold`` bits agree on at least one full band — so candidate
       pairs are exactly the rows that collide in any single band-bucket.
    2. Candidates are then verified with the full Hamming distance check.

    Falls back to a quadratic pair walk when ``threshold`` is high enough
    that bands would shrink below 4 bits (effectively useless as bucket
    keys) — at that point the index degenerates and the linear path is
    no slower in practice while remaining exact.

    Args:
        fingerprints: Per-row simhashes (``0`` is sentinel for empty rows).
        threshold: Hamming-distance cutoff; default 3 ≈ 95 % similarity.
        bits: Fingerprint width in bits. Default matches
            :func:`compute_simhash`.

    Pairs are returned in row-index order to keep the output stable across
    runs and across the brute-force / LSH paths.
    """
    bands = _band_count_for_threshold(threshold, bits)
    if bands == 0:
        return _find_near_duplicates_brute(fingerprints, threshold)

    # Bucket: (band_index, band_value) -> sorted list of row indices.
    buckets: Dict[Tuple[int, int], List[int]] = {}
    for idx, fp in enumerate(fingerprints):
        if fp == 0:
            continue
        for band_idx, band_val in enumerate(_split_into_bands(fp, bands, bits)):
            buckets.setdefault((band_idx, band_val), []).append(idx)

    seen: set = set()
    pairs: List[Tuple[int, int, int]] = []
    for indices in buckets.values():
        if len(indices) < 2:
            continue
        for left_pos in range(len(indices)):
            i = indices[left_pos]
            fp_i = fingerprints[i]
            for right_pos in range(left_pos + 1, len(indices)):
                j = indices[right_pos]
                if (i, j) in seen:
                    continue
                seen.add((i, j))
                distance = hamming_distance(fp_i, fingerprints[j])
                if distance <= threshold:
                    pairs.append((i, j, distance))

    pairs.sort(key=lambda triple: (triple[0], triple[1]))
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


def _read_jsonl_split(path: Path) -> Iterator[Tuple[Any, bool, bool]]:
    """Streaming JSONL reader. Yields ``(row, parse_error, decode_error)``.

    Phase 11.5 promoted this from a buffered ``(rows, parse_errors,
    decode_errors)`` tuple to a generator so the audit pipeline can process
    one line at a time. RAM use on a 100 K-row split drops from O(n) raw
    rows + O(n) text payloads (~hundreds of MB) to a handful of metric
    aggregators plus the ``n``-element fingerprint list (8 bytes/row).

    Per-line semantics are unchanged:

    * UTF-8 decode is permissive (``errors="replace"``) — a single mojibake
      line never aborts the whole audit. Any line containing the U+FFFD
      replacement char is reported via ``decode_error=True`` so the
      operator gets a structured signal alongside the row.
    * ``json.JSONDecodeError`` is caught per line; the offending line is
      surfaced as ``(None, parse_error=True, decode_error=...)`` so
      downstream aggregators can count it without the row poisoning the
      schema / payload pipelines.
    * Yielded rows may be non-dict JSON (lists, scalars); downstream
      :func:`_extract_text_payload` and :func:`_audit_split` guard
      ``isinstance(row, dict)``.

    ``OSError`` from the initial ``open()`` is propagated to the caller —
    that is the expected signal for "this split is unreachable / unreadable".
    """
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line_number, raw_line in enumerate(fh, start=1):
            line = raw_line.strip()
            if not line:
                continue
            decode_error = "�" in line
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                logger.warning("Skipping malformed JSONL line %d in %s: %s", line_number, path, exc)
                yield None, True, decode_error
                continue
            yield row, False, decode_error


_PROGRESS_INTERVAL: int = 5000
"""Emit a progress log every N rows when a split is large enough that the
audit's silent stretch is over a few seconds. Threshold picked so smoke
tests / quickstart audits stay quiet but real corpora surface signal."""


_LANG_SAMPLE_SIZE: int = 200
"""How many text-bearing payloads we sample for language detection. Bounded
so a 100 K-row corpus does not pay 100 K langdetect calls — the top-3
distribution is well-approximated by the first ~200 detections."""


@dataclass
class _StreamingAggregator:
    """Single-pass collector for per-split audit metrics.

    Owns one concern: turn the ``(row, parse_err, decode_err)`` stream
    coming out of :func:`_read_jsonl_split` into the structured ``info``
    dict the audit report consumes. Holding state on a dataclass keeps
    the streaming loop in :func:`_audit_split` flat and the field roles
    self-documenting; nothing else in the module instantiates this.
    """

    sample_count: int = 0
    parse_errors: int = 0
    decode_errors: int = 0
    non_object_rows: int = 0
    null_or_empty: int = 0
    keysets: List[frozenset] = field(default_factory=list)
    seen_columns: "OrderedDict[str, None]" = field(default_factory=OrderedDict)
    text_lengths: List[int] = field(default_factory=list)
    fingerprints: List[int] = field(default_factory=list)
    pii_counts: Dict[str, int] = field(default_factory=dict)
    lang_sample: List[str] = field(default_factory=list)


def _record_schema_for_dict(agg: _StreamingAggregator, row: Dict[str, Any]) -> None:
    keys = frozenset(row.keys())
    agg.keysets.append(keys)
    for col in keys:
        agg.seen_columns.setdefault(col, None)


def _record_text_metrics(agg: _StreamingAggregator, payload: str) -> None:
    agg.text_lengths.append(len(payload))
    if len(agg.lang_sample) < _LANG_SAMPLE_SIZE:
        agg.lang_sample.append(payload)
    agg.fingerprints.append(compute_simhash(payload))
    for kind, count in detect_pii(payload).items():
        agg.pii_counts[kind] = agg.pii_counts.get(kind, 0) + count


def _ingest_row(agg: _StreamingAggregator, row: Any, parse_err: bool, decode_err: bool) -> None:
    """Fold one stream element into the aggregator. Single-concern helper."""
    if decode_err:
        agg.decode_errors += 1
    if parse_err:
        agg.parse_errors += 1
        return

    agg.sample_count += 1

    if not isinstance(row, dict):
        # Non-dict rows are valid JSON but the audit's text-payload pipeline
        # cannot extract anything useful. Track them separately from the
        # null/empty bucket so an operator can tell shape problems apart
        # from missing-text problems.
        agg.non_object_rows += 1
        agg.null_or_empty += 1
        agg.fingerprints.append(0)
        return

    _record_schema_for_dict(agg, row)
    payload = _extract_text_payload(row)
    if not payload:
        agg.null_or_empty += 1
        agg.fingerprints.append(0)
        return
    _record_text_metrics(agg, payload)


def _aggregator_to_info(
    split_name: str,
    agg: _StreamingAggregator,
    *,
    near_dup_threshold: int,
) -> Dict[str, Any]:
    """Render the aggregator state as the per-split ``info`` payload."""
    info: Dict[str, Any] = {"sample_count": agg.sample_count}
    if agg.sample_count == 0:
        info["near_duplicate_pairs"] = 0
        return info

    columns_list = list(agg.seen_columns)
    if columns_list:
        info["columns"] = columns_list

    if agg.keysets:
        most_common_keyset, _ = Counter(agg.keysets).most_common(1)[0]
        base_columns = set(most_common_keyset)
        drift_columns = [c for c in columns_list if c not in base_columns]
        if drift_columns:
            info["schema_drift_columns"] = drift_columns

    if agg.non_object_rows:
        info["non_object_rows"] = agg.non_object_rows

    if agg.text_lengths:
        info["text_length"] = _length_stats(agg.text_lengths)
    info["null_or_empty_count"] = agg.null_or_empty
    info["null_or_empty_rate"] = round(agg.null_or_empty / agg.sample_count, 4)

    languages_top3 = _compute_top_languages(agg.lang_sample)
    if languages_top3:
        info["languages_top3"] = languages_top3

    info["simhash_distinct"] = len({fp for fp in agg.fingerprints if fp != 0})

    if agg.pii_counts:
        info["pii_counts"] = dict(agg.pii_counts)

    if agg.sample_count >= _PROGRESS_INTERVAL:
        logger.info(
            "audit/%s: scanning for near-duplicates (LSH-banded; %d rows)…",
            split_name,
            agg.sample_count,
        )
    within_pairs = find_near_duplicates(agg.fingerprints, threshold=near_dup_threshold)
    info["near_duplicate_pairs"] = len(within_pairs)
    return info


def _compute_top_languages(sample: List[str]) -> List[Dict[str, Any]]:
    """Top-3 languages over the ``sample`` list. Empty ``sample`` → empty list."""
    counts: Dict[str, int] = {}
    for text in sample:
        lang = _detect_language(text)
        if lang:
            counts[lang] = counts.get(lang, 0) + 1
    if not counts:
        return []
    top3 = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:3]
    return [{"code": code, "count": n} for code, n in top3]


def _audit_split(
    split_name: str,
    path: Path,
    *,
    near_dup_threshold: int = DEFAULT_NEAR_DUP_HAMMING,
) -> Tuple[Dict[str, Any], List[int], Dict[str, int], int, int]:
    """Stream a JSONL split into a metrics record.

    Phase 11.5 streamed this end-to-end: the function consumes
    :func:`_read_jsonl_split` row-by-row and folds each line straight
    into a :class:`_StreamingAggregator`. Memory is bounded to
    ``O(n_fingerprints + n_distinct_keysets)`` plus a 200-row language
    sample — no list of full rows or per-row payloads is retained.

    Returns:
        ``(info_dict, fingerprints, pii_counts, parse_errors, decode_errors)``.
        Caller (:func:`_process_split`) uses the trailing two integers to
        annotate the split with its data-integrity counts.
    """
    agg = _StreamingAggregator()
    for row, parse_err, decode_err in _read_jsonl_split(path):
        _ingest_row(agg, row, parse_err, decode_err)
        if agg.sample_count and agg.sample_count % _PROGRESS_INTERVAL == 0:
            logger.info(
                "audit/%s: %d rows scanned (streaming)…",
                split_name,
                agg.sample_count,
            )

    info = _aggregator_to_info(split_name, agg, near_dup_threshold=near_dup_threshold)
    return info, list(agg.fingerprints), dict(agg.pii_counts), agg.parse_errors, agg.decode_errors


def _build_band_index(
    fingerprints: List[int],
    bands: int,
    bits: int,
) -> Dict[Tuple[int, int], List[int]]:
    """Bucket ``fingerprints`` by (band_index, band_value) for LSH lookups."""
    buckets: Dict[Tuple[int, int], List[int]] = {}
    for idx, fp in enumerate(fingerprints):
        if fp == 0:
            continue
        for band_idx, band_val in enumerate(_split_into_bands(fp, bands, bits)):
            buckets.setdefault((band_idx, band_val), []).append(idx)
    return buckets


def _count_leaked_rows(
    source: List[int],
    target: List[int],
    threshold: int,
    *,
    bits: int = 64,
) -> int:
    """Rows in ``source`` whose nearest neighbour in ``target`` is within ``threshold``.

    Uses the same LSH banding shape as :func:`find_near_duplicates` so a
    cross-split overlap audit on a 100 K-row train + 10 K-row test no
    longer needs the full ``100K × 10K`` Hamming sweep. Falls back to a
    linear scan when banding cannot be configured (edge thresholds).
    """
    bands = _band_count_for_threshold(threshold, bits)
    if bands == 0:
        return sum(
            1
            for fp in source
            if fp != 0 and any(other != 0 and hamming_distance(fp, other) <= threshold for other in target)
        )

    target_index = _build_band_index(target, bands, bits)
    if not target_index:
        return 0

    leaked = 0
    for fp in source:
        if fp == 0:
            continue
        # Walk the source row's bands; verify any candidate hit. ``seen`` is
        # local per-source-row so the early-exit short-circuits as soon as
        # ANY target row passes the Hamming check.
        seen: set = set()
        matched = False
        for band_idx, band_val in enumerate(_split_into_bands(fp, bands, bits)):
            candidates = target_index.get((band_idx, band_val))
            if not candidates:
                continue
            for j in candidates:
                if j in seen:
                    continue
                seen.add(j)
                if hamming_distance(fp, target[j]) <= threshold:
                    matched = True
                    break
            if matched:
                break
        if matched:
            leaked += 1
    return leaked


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
    """Stream + audit one split. Tolerates per-split filesystem failures.

    The streaming :func:`_audit_split` opens ``path`` lazily inside
    :func:`_read_jsonl_split`, so an ``OSError`` (permission denied,
    ENOSPC, IsADirectoryError, …) bubbles up here and is converted into
    a structured per-split error rather than aborting the whole audit.
    Other splits in the same directory continue uninterrupted.
    """
    logger.info("audit: scanning split '%s' (%s)", split_name, path.name)
    try:
        info, fingerprints, pii_split, parse_errors, decode_errors = _audit_split(
            split_name,
            path,
            near_dup_threshold=near_dup_threshold,
        )
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
        row_count=info.get("sample_count", 0),
        parse_errors=parse_errors,
        decode_errors=decode_errors,
        split_notes=split_notes,
    )


def _build_pii_severity(pii_summary: Dict[str, int]) -> Dict[str, Any]:
    """Aggregate PII counts into a severity-tiered breakdown.

    Maps each detected category through :data:`PII_SEVERITY` and emits a
    structured payload that compliance reviewers can parse at a glance:
    a per-tier total, a worst-tier verdict, and a per-type breakdown so
    nothing is lost from the underlying flat counts. Categories absent
    from :data:`PII_SEVERITY` (forward-compat for new types) fall back to
    ``unknown``.
    """
    if not pii_summary:
        return {
            "total": 0,
            "by_tier": {tier: 0 for tier in PII_SEVERITY_ORDER},
            "by_type": {},
            "worst_tier": None,
        }

    by_tier: Dict[str, int] = {tier: 0 for tier in PII_SEVERITY_ORDER}
    by_type: Dict[str, Dict[str, Any]] = {}
    total = 0
    worst_tier_idx: Optional[int] = None

    for kind, count in pii_summary.items():
        if count <= 0:
            continue
        tier = PII_SEVERITY.get(kind, "unknown")
        by_type[kind] = {"count": count, "tier": tier}
        if tier in by_tier:
            by_tier[tier] += count
        else:  # pragma: no cover — defensive for future PII categories
            by_tier.setdefault(tier, 0)
            by_tier[tier] += count
        total += count
        if tier in PII_SEVERITY_ORDER:
            idx = PII_SEVERITY_ORDER.index(tier)
            if worst_tier_idx is None or idx < worst_tier_idx:
                worst_tier_idx = idx

    worst_tier = PII_SEVERITY_ORDER[worst_tier_idx] if worst_tier_idx is not None else None
    return {
        "total": total,
        "by_tier": by_tier,
        "by_type": by_type,
        "worst_tier": worst_tier,
    }


def _pii_summary_notes(pii_summary: Dict[str, int], pii_severity: Dict[str, Any]) -> List[str]:
    """Operator-actionable note (or "none flagged") for the aggregate PII counts.

    Severity-tier-aware: when a critical-tier category fires (credit card,
    IBAN), the note leads with that verdict so it can't be missed under a
    pile of lower-tier matches. Falls back to the original neutral message
    when nothing is flagged or the severity payload is empty.
    """
    if not pii_summary:
        return ["No PII flagged. (Regex-based detector — false negatives possible.)"]
    flag_total = sum(pii_summary.values())
    breakdown = ", ".join(f"{k}={v}" for k, v in sorted(pii_summary.items()))
    worst_tier = pii_severity.get("worst_tier") if pii_severity else None
    severity_lead = f"WORST tier: {worst_tier.upper()}. " if worst_tier else ""
    return [
        f"{severity_lead}PII flags surfaced ({flag_total} total: {breakdown}). "
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
    pii_severity = _build_pii_severity(pii_summary)
    notes.extend(_pii_summary_notes(pii_summary, pii_severity))
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
        pii_severity=pii_severity,
        near_duplicate_summary={
            "hamming_threshold": near_dup_threshold,
            "pairs_per_split": near_dup_pairs,
        },
        notes=notes,
    )

    if output_dir:
        out_dir = Path(output_dir).expanduser().resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(out_dir / "data_audit_report.json", asdict(report))

    return report


def _atomic_write_json(target: Path, payload: Dict[str, Any]) -> None:
    """Write ``payload`` to ``target`` via tempfile + atomic rename.

    Phase 11.5 hardening: previously the audit report was written with a
    plain ``open()`` + ``json.dump``. A crash mid-write left a half-baked
    file at the canonical path, so the next pipeline step would either
    parse garbage or trip the "missing report" branch silently. Routing
    through :class:`tempfile.NamedTemporaryFile` in the same directory and
    then ``os.replace`` keeps the canonical path either fully present
    (post-crash readers see the previous good report) or atomically
    swapped with a complete one. ``newline="\\n"`` pins LF terminators
    so the file is byte-identical across Windows/Linux/macOS — important
    because the EU AI Act governance bundle inlines this exact JSON.
    """
    tmp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=str(target.parent),
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as fh:
            tmp_path = Path(fh.name)
            json.dump(payload, fh, indent=2, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, target)
        tmp_path = None
        logger.info("Wrote audit report: %s", target)
    finally:
        if tmp_path is not None and tmp_path.exists():
            # Best-effort cleanup so a half-written .tmp doesn't litter the
            # output dir if os.replace itself raised (rare — same FS).
            try:
                tmp_path.unlink()
            except OSError:  # pragma: no cover — defensive
                pass


def _split_has_findings(info: Dict[str, Any]) -> bool:
    """A split is "interesting" when any non-trivial signal is present.

    Used by :func:`summarize_report` in non-verbose mode to suppress
    splits with zero findings. The criteria stay loose on purpose —
    operators expect to see every split that has *anything* worth
    reviewing (errors, drift, leakage, PII, near-duplicates, decode
    issues), and only the all-clean rows get folded into a tail summary.
    """
    if "error" in info:
        return True
    for key in (
        "null_or_empty_count",
        "near_duplicate_pairs",
        "pii_counts",
        "schema_drift_columns",
        "non_object_rows",
        "parse_errors",
        "decode_errors",
    ):
        value = info.get(key)
        if isinstance(value, dict) and value:
            return True
        if isinstance(value, list) and value:
            return True
        if isinstance(value, int) and value > 0:
            return True
    return False


def _render_split_block(split_name: str, info: Dict[str, Any]) -> List[str]:
    """Operator-friendly rendering of one split's metrics. One concern per call."""
    block: List[str] = [f"  └─ {split_name}: n={info.get('sample_count', 0)}"]
    if "error" in info:
        block.append(f"     ERROR        : {info['error']}")
        return block
    text_len = info.get("text_length") or {}
    if text_len:
        block.append(
            f"     length  min={text_len['min']} max={text_len['max']} mean={text_len['mean']} p95={text_len['p95']}"
        )
    if info.get("null_or_empty_count"):
        block.append(f"     null/empty: {info['null_or_empty_count']} ({info['null_or_empty_rate'] * 100:.1f}%)")
    if info.get("near_duplicate_pairs"):
        block.append(f"     near-duplicate pairs: {info['near_duplicate_pairs']}")
    if info.get("languages_top3"):
        tops = ", ".join(f"{e['code']}={e['count']}" for e in info["languages_top3"])
        block.append(f"     languages (top-3): {tops}")
    if info.get("pii_counts"):
        pii = ", ".join(f"{k}={v}" for k, v in sorted(info["pii_counts"].items()))
        block.append(f"     PII             : {pii}")
    if info.get("schema_drift_columns"):
        block.append(f"     schema drift    : {', '.join(info['schema_drift_columns'])}")
    return block


def _render_pii_severity(severity: Dict[str, Any]) -> List[str]:
    """Render the PII severity summary (or nothing when no flags fired)."""
    if not severity or not severity.get("total"):
        return []
    out = [f"  PII severity   : worst tier = {severity.get('worst_tier') or 'n/a'}"]
    by_tier = severity.get("by_tier", {})
    nonzero = [(tier, count) for tier, count in by_tier.items() if count]
    if nonzero:
        breakdown = ", ".join(f"{tier}={count}" for tier, count in nonzero)
        out.append(f"     by tier      : {breakdown}")
    return out


def summarize_report(report: AuditReport, *, verbose: bool = False) -> str:
    """Render an :class:`AuditReport` as a multi-line operator-facing summary.

    Default (``verbose=False``): splits with zero findings are folded into
    a single "N split(s) clean" line. This keeps the multi-split summary
    short on a healthy dataset while still surfacing every interesting
    signal — error, drift, leakage, PII, decode issues, near-duplicates.
    Pass ``verbose=True`` to print every split unconditionally.
    """
    lines = [
        "Data audit summary",
        f"  Source        : {report.source_path}",
        f"  Total samples : {report.total_samples}",
        f"  Splits        : {', '.join(report.splits)}",
    ]

    interesting: List[Tuple[str, Dict[str, Any]]] = []
    clean: List[str] = []
    for split_name, info in report.splits.items():
        if verbose or _split_has_findings(info):
            interesting.append((split_name, info))
        else:
            clean.append(split_name)

    for split_name, info in interesting:
        lines.extend(_render_split_block(split_name, info))

    if clean and not verbose:
        lines.append(f"  └─ ({len(clean)} clean split(s): {', '.join(clean)} — pass verbose=True to expand)")

    lines.extend(_render_pii_severity(report.pii_severity))

    if report.cross_split_overlap.get("pairs"):
        lines.append("  Cross-split leakage:")
        for pair_name, payload in report.cross_split_overlap["pairs"].items():
            lines.append(f"    {pair_name}: {payload}")
    return "\n".join(lines)
