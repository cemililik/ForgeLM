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
    # Luhn-validated (see _is_credit_card)
    "credit_card": re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
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


def detect_pii(text: str) -> Dict[str, int]:
    """Return a ``{pii_type: count}`` map for the given string.

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


def mask_pii(text: str, replacement: str = "[REDACTED]") -> str:
    """Return ``text`` with every detected PII span replaced by ``replacement``.

    Pattern precedence is the dict order in :data:`_PII_PATTERNS` — most
    specific patterns first (email, IBAN, credit card, national IDs) so a
    span that would match multiple categories is attributed to the narrower
    one. Phone is scanned LAST and is anchored to ``+CC`` or ``(area)``
    formats so bare digit runs (timestamps, IDs, dates) do not collide.
    """
    if not text or not isinstance(text, str):
        return text
    out = text
    for pii_type, pattern in _PII_PATTERNS.items():

        def _replace(match: re.Match, _t: str = pii_type) -> str:
            if _validate_match(_t, match.group(0)):
                return replacement
            return match.group(0)

        out = pattern.sub(_replace, out)
    return out


# ---------------------------------------------------------------------------
# Simhash + near-duplicate detection
# ---------------------------------------------------------------------------


_TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)


def _tokenize(text: str) -> List[str]:
    return [tok.lower() for tok in _TOKEN_PATTERN.findall(text or "")]


def compute_simhash(text: str, *, bits: int = 64) -> int:
    """64-bit simhash over case-folded word tokens.

    Uses MD5 (non-cryptographic use — pure mixing), then per-bit majority
    voting weighted by token frequency to produce the final fingerprint.
    Empty input → ``0``.
    """
    tokens = _tokenize(text)
    if not tokens:
        return 0

    weights: Dict[str, int] = {}
    for token in tokens:
        weights[token] = weights.get(token, 0) + 1

    bit_scores = [0] * bits
    for token, weight in weights.items():
        digest = hashlib.md5(token.encode("utf-8"), usedforsecurity=False).digest()
        token_hash = int.from_bytes(digest[: bits // 8], "big")
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


def _read_jsonl_split(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                logger.warning("Skipping malformed JSONL line %d in %s: %s", line_number, path, exc)
    return rows


def _audit_split(split_name: str, rows: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], List[int], Dict[str, int]]:
    """Per-split metrics. Returns (info_dict, simhashes_list, pii_counts_dict)."""
    info: Dict[str, Any] = {"sample_count": len(rows)}
    if not rows:
        return info, [], {}

    # Schema is the *union* of keys across rows — heterogeneous BYOD JSONL
    # often has optional fields (e.g. only some rows have `gold_answer`).
    # Reading just rows[0].keys() would silently drop those extras.
    seen_columns: Dict[str, None] = {}  # ordered set
    for row in rows:
        if isinstance(row, dict):
            for col in row.keys():
                seen_columns.setdefault(col, None)
    info["columns"] = list(seen_columns)
    base_columns = set(rows[0].keys()) if isinstance(rows[0], dict) else set()
    drift_columns = [c for c in seen_columns if c not in base_columns]
    if drift_columns:
        info["schema_drift_columns"] = drift_columns

    text_payloads: List[str] = []
    null_or_empty = 0
    for row in rows:
        payload = _extract_text_payload(row)
        if not payload:
            null_or_empty += 1
        text_payloads.append(payload)

    lengths = [len(t) for t in text_payloads if t]
    info["text_length"] = _length_stats(lengths)
    info["null_or_empty_count"] = null_or_empty
    info["null_or_empty_rate"] = round(null_or_empty / len(rows), 4)

    # Language: aggregate from a sample to bound cost on large splits.
    sample = text_payloads[: min(200, len(text_payloads))]
    lang_counts: Dict[str, int] = {}
    for t in sample:
        lang = _detect_language(t)
        if lang:
            lang_counts[lang] = lang_counts.get(lang, 0) + 1
    if lang_counts:
        top3 = sorted(lang_counts.items(), key=lambda kv: kv[1], reverse=True)[:3]
        info["languages_top3"] = [{"code": code, "count": n} for code, n in top3]

    fingerprints = [compute_simhash(t) for t in text_payloads]
    info["simhash_distinct"] = len({fp for fp in fingerprints if fp != 0})

    pii_counts_split: Dict[str, int] = {}
    for t in text_payloads:
        for kind, n in detect_pii(t).items():
            pii_counts_split[kind] = pii_counts_split.get(kind, 0) + n
    if pii_counts_split:
        info["pii_counts"] = pii_counts_split

    return info, fingerprints, pii_counts_split


def _cross_split_overlap(
    fingerprints_by_split: Dict[str, List[int]],
    threshold: int,
) -> Dict[str, Any]:
    """Pairwise leakage report across train/validation/test splits."""
    report: Dict[str, Any] = {"hamming_threshold": threshold, "pairs": {}}
    splits = list(fingerprints_by_split.keys())
    for i, a in enumerate(splits):
        fp_a = [fp for fp in fingerprints_by_split[a] if fp != 0]
        if not fp_a:
            continue
        for j in range(i + 1, len(splits)):
            b = splits[j]
            fp_b_set = {fp for fp in fingerprints_by_split[b] if fp != 0}
            if not fp_b_set:
                continue
            shared = sum(1 for fp in fp_a if any(hamming_distance(fp, other) <= threshold for other in fp_b_set))
            report["pairs"][f"{a}__{b}"] = {
                "leaked_rows_in_{}".format(a): shared,
                "leak_rate": round(shared / len(fp_a), 4) if fp_a else 0.0,
            }
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


def _resolve_input(source: str) -> Tuple[Dict[str, Path], List[str]]:
    """Map the user-supplied path to a ``{split_name: path}`` dict + notes.

    Two layouts are supported:
    * Single ``.jsonl`` file → treated as the ``train`` split.
    * Directory with files matching canonical names (``train.jsonl`` /
      ``validation.jsonl`` / ``test.jsonl``) or common aliases (``dev`` /
      ``val`` / ``valid`` / ``eval`` / ``holdout``).

    Returns a ``(splits_dict, notes_list)`` tuple. ``notes_list`` carries
    operator-relevant signals (alias collapse, pseudo-split fallback)
    surfaced both in the report and in the CLI summary.
    """
    src = Path(source).expanduser().resolve()
    notes: List[str] = []
    if src.is_file():
        return {"train": src}, notes
    if src.is_dir():
        layouts: Dict[str, Path] = {}
        # Canonical + alias discovery.
        for stem, canonical in _SPLIT_ALIASES.items():
            candidate = src / f"{stem}.jsonl"
            if not candidate.is_file():
                continue
            if canonical in layouts:
                # Two files map to the same canonical split — surface this
                # rather than silently picking one.
                notes.append(
                    f"both '{layouts[canonical].name}' and '{candidate.name}' map to "
                    f"the '{canonical}' split; using the first one. Rename to disambiguate."
                )
                continue
            if stem != canonical:
                notes.append(f"'{candidate.name}' treated as the '{canonical}' split.")
            layouts[canonical] = candidate
        if layouts:
            return layouts, notes

        # No canonical / alias hits — last-resort fallback: every .jsonl
        # becomes its own pseudo-split. Cross-split leakage analysis here
        # is misleading (those files probably aren't a real train/test
        # partition), so warn loudly.
        for jsonl in sorted(src.glob("*.jsonl")):
            layouts[jsonl.stem] = jsonl
        if layouts:
            notes.append(
                f"no canonical split files found in '{src}'. "
                "Each .jsonl is being audited as its own pseudo-split — "
                "cross-split leakage analysis is meaningless without a real partition."
            )
            logger.warning(notes[-1])
            return layouts, notes
    raise FileNotFoundError(
        f"Audit input not found or empty: '{src}'. "
        f"Pass a .jsonl file or a directory containing train.jsonl / validation.jsonl / test.jsonl."
    )


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

    for split_name, path in splits_paths.items():
        # Bug 31: tolerate per-split filesystem failures (permissions, EIO,
        # truncated files mid-read). A bad split should be reported, not
        # abort the whole audit — operators usually want a partial report
        # over no report.
        try:
            rows = _read_jsonl_split(path)
        except OSError as exc:
            logger.warning("Could not read split '%s' (%s): %s — skipping.", split_name, path, exc)
            splits_info[split_name] = {"error": f"read_failed: {exc}", "path": str(path)}
            fingerprints_by_split[split_name] = []
            notes.append(f"split '{split_name}' skipped (read failure: {exc})")
            continue

        info, fingerprints, pii_split = _audit_split(split_name, rows)
        splits_info[split_name] = info
        fingerprints_by_split[split_name] = fingerprints
        total_samples += len(rows)

        for kind, count in pii_split.items():
            pii_summary[kind] = pii_summary.get(kind, 0) + count

        within_pairs = find_near_duplicates(fingerprints, threshold=near_dup_threshold)
        near_dup_pairs[split_name] = len(within_pairs)
        info["near_duplicate_pairs"] = len(within_pairs)

    cross = _cross_split_overlap(fingerprints_by_split, near_dup_threshold)

    # Actionable, not just informational — Bug 34.
    if not pii_summary:
        notes.append("No PII flagged. (Regex-based detector — false negatives possible.)")
    else:
        flag_total = sum(pii_summary.values())
        breakdown = ", ".join(f"{k}={v}" for k, v in sorted(pii_summary.items()))
        notes.append(
            f"PII flags surfaced ({flag_total} total: {breakdown}). "
            "Review before publishing; mask with `forgelm ingest --pii-mask` "
            "or use `forgelm.data_audit.mask_pii` programmatically."
        )

    cross_pairs = cross.get("pairs", {}) or {}
    leaking = [name for name, payload in cross_pairs.items() if payload.get("leak_rate", 0) > 0]
    if leaking:
        notes.append(
            f"Cross-split leakage detected in {len(leaking)} pair(s): {', '.join(leaking)}. "
            "Re-shuffle splits before benchmarking — leaked rows poison test fidelity."
        )

    near_dup_total = sum(near_dup_pairs.values())
    if near_dup_total > 0:
        notes.append(
            f"{near_dup_total} near-duplicate pair(s) found within splits. "
            "Inspect; identical chunks waste training compute and can overweight specific phrasing."
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
        with open(out_path, "w", encoding="utf-8") as fh:
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
