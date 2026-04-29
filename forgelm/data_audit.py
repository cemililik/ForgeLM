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
# non-cryptographic 64-bit hash. The Python-level speedup is modest — local
# microbenchmark (Apple Silicon, Python 3.11.2, xxhash 3.7.0) measured ~1.3×
# on the raw per-digest cost and ~1.05× end-to-end inside compute_simhash
# (the lru_cache below absorbs most repeats anyway). xxhash's well-known
# "4-10× faster than crypto hashes" figure refers to C-level pure-hash
# benchmarks; the Python wrapping (encode → call → intdigest) levels the
# playing field. We keep xxhash as the optional backend mostly for forward
# compatibility / parity with other simhash implementations and fall back to
# BLAKE2b cleanly when the dependency is missing so a bare install still
# produces identical fingerprints across releases.
try:  # pragma: no cover — exercised by the dedicated extras-skip tests
    import xxhash as _xxhash

    _HAS_XXHASH = True
except ImportError:  # pragma: no cover
    _xxhash = None
    _HAS_XXHASH = False


# C.3: optional numpy for vectorised bit-unpacking inside compute_simhash.
# The pure-Python path loops `bits` times per token; numpy unpacks the full
# `bits`-wide integer in one matrix operation (tokens × bits) and reduces
# along the token axis with a single dot product.  Speedup is ~4–8× on
# corpora with >1 K unique tokens per record; negligible for short texts
# (lru_cache already handles repeated tokens).
try:  # pragma: no cover — optional accelerator
    import numpy as _np

    _HAS_NUMPY = True
except ImportError:  # pragma: no cover
    _np = None  # type: ignore[assignment]
    _HAS_NUMPY = False


# Phase 12: optional ``datasketch`` backend for MinHash LSH near-duplicate
# detection. Default audit stays on the simhash + LSH band path (Phase 11.5)
# which is exact at ``threshold=3`` and bounded ~50K rows. ``--dedup-method
# minhash`` opts into LSH-banded MinHash, which is the industry standard for
# >50K-row corpora (NeMo Curator, Dolma, RedPajama). MinHash is approximate
# (Jaccard with permutation noise) — that's why simhash stays default.
try:  # pragma: no cover — exercised by the dedicated extras-skip tests
    from datasketch import MinHash as _MinHash
    from datasketch import MinHashLSH as _MinHashLSH

    _HAS_DATASKETCH = True
except ImportError:  # pragma: no cover
    _MinHash = None  # type: ignore[assignment]
    _MinHashLSH = None  # type: ignore[assignment]
    _HAS_DATASKETCH = False


# Phase 12.5: optional Presidio ML-NER PII detection. Layered ON TOP of
# the regex detector so the default audit keeps its zero-extra-deps
# guarantee. Presidio + spaCy are heavyweight (≈ 50 MB model download),
# so we stay strictly opt-in and fail soft when missing — the regex set
# already covers the GDPR-mandated structured identifiers (email, phone,
# IBAN, credit card, national IDs) that the audit's compliance contract
# is built around. ML adds the *unstructured* identifiers regex inherently
# misses: person names, organisations, locations.
try:  # pragma: no cover — exercised by the dedicated extras-skip tests
    from presidio_analyzer import AnalyzerEngine as _PresidioAnalyzer

    _HAS_PRESIDIO = True
except ImportError:  # pragma: no cover
    _PresidioAnalyzer = None  # type: ignore[assignment]
    _HAS_PRESIDIO = False


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


# Phase 12.5: severity for the ML-NER detector (Presidio adapter).  These
# categories sit alongside the regex set and feed the same pii_severity
# block, which is why they share the ``critical/high/medium/low`` tier
# vocabulary.  Entries are deliberately on the lower end of the tier
# table because NER false-positive rates are materially higher than the
# regex-anchored detectors (a model name, a city, or an organization
# string can be flagged with no privacy impact); compliance reviewers
# can still upgrade the tier locally if their corpus warrants it.
PII_ML_SEVERITY: Dict[str, str] = {
    "person": "medium",
    "organization": "low",
    "location": "low",
}


PII_ML_TYPES: Tuple[str, ...] = tuple(PII_ML_SEVERITY.keys())
"""Canonical category names for ML-detected PII.  Disjoint from
:data:`PII_TYPES` (regex categories) so the two detectors can run side
by side without double-counting the same span."""


# Columns we treat as text payloads when computing length / language / dedup.
# Order matters: first match wins per row.
_TEXT_COLUMNS: Tuple[str, ...] = ("text", "content", "completion", "prompt")


# Default Hamming-distance threshold for "near-duplicate" via 64-bit simhash.
# 3 bits ≈ ~95% similarity at 64-bit width — same threshold the simhash paper
# uses for the canonical web-page-dedup deployment.
DEFAULT_NEAR_DUP_HAMMING: int = 3


# Phase 12: defaults for the optional MinHash LSH dedup path.
DEFAULT_MINHASH_JACCARD: float = 0.85
"""Jaccard-similarity threshold for MinHash LSH. ``0.85`` mirrors the
``threshold=3 → ≈95 %`` simhash default in spirit — the two approaches
report the same relative class of near-duplicates on real corpora,
within MinHash's permutation noise."""

DEFAULT_MINHASH_NUM_PERM: int = 128
"""Permutation count for ``datasketch.MinHash``. ``128`` is the
``datasketch`` default and the standard balance: enough hash functions
for stable Jaccard estimates, low enough that per-row cost stays in
the same ballpark as simhash."""

DEDUP_METHODS: Tuple[str, ...] = ("simhash", "minhash")
"""Allowed values for ``audit_dataset(..., dedup_method=...)`` and
``forgelm audit --dedup-method ...``. ``simhash`` is the default and
the only method that does not require an optional dependency."""


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
    # Phase 12: aggregate counts for code/credential leakage and (opt-in)
    # heuristic quality flags. Both are additive — older consumers that
    # ignored them keep working byte-identically; the fields stay empty
    # dicts on default audits with no findings.
    secrets_summary: Dict[str, int] = field(default_factory=dict)
    quality_summary: Dict[str, Any] = field(default_factory=dict)
    # Phase 12.5: optional Google Croissant 1.0 dataset card. Empty dict
    # by default so existing consumers see byte-identical output; set
    # via ``audit_dataset(..., emit_croissant=True)`` or ``--croissant``.
    croissant: Dict[str, Any] = field(default_factory=dict)
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
# Phase 12.5: optional Presidio ML-NER PII adapter
# ---------------------------------------------------------------------------


# Conventional spaCy model name per language code. Covers the languages
# spaCy publishes a maintained ``*_core_news_lg`` / ``*_core_web_lg``
# model for; operators auditing in a language not in this map should
# pass ``"xx"`` for the multilingual fallback (and install
# ``xx_ent_wiki_sm``) or hand-build a Presidio ``NlpEngine`` and feed
# it to :func:`audit_dataset` programmatically. The map is small on
# purpose — auto-mapping more languages without verifying each model's
# NER quality risks silent under-detection in compliance-critical
# workflows.
_SPACY_MODEL_FOR_LANGUAGE: Dict[str, str] = {
    "en": "en_core_web_lg",
    "de": "de_core_news_lg",
    "es": "es_core_news_lg",
    "fr": "fr_core_news_lg",
    "it": "it_core_news_lg",
    "ja": "ja_core_news_lg",
    "ko": "ko_core_news_lg",
    "nl": "nl_core_news_lg",
    "pl": "pl_core_news_lg",
    "pt": "pt_core_news_lg",
    "ru": "ru_core_news_lg",
    "zh": "zh_core_web_lg",
    # Multilingual fallback — coarser NER but works for any Unicode
    # script; useful for languages without a dedicated spaCy model
    # (e.g. Turkish, Arabic at time of writing).
    "xx": "xx_ent_wiki_sm",
}


# Presidio analyzer is heavy to construct (loads spaCy + a NER model on
# first call), so we cache instances per-language. ``maxsize=8`` covers
# the realistic set of audit-language combinations a single process
# would request without unbounded growth; test code blows the cache via
# ``cache_clear()``.
@lru_cache(maxsize=8)
def _get_presidio_analyzer(language: str = "en") -> Any:
    """Return a cached :class:`presidio_analyzer.AnalyzerEngine` for ``language``.

    English uses Presidio's default constructor (loads ``en_core_web_lg``
    via spaCy). Non-English builds an :class:`NlpEngineProvider` keyed
    on the conventional spaCy model from
    :data:`_SPACY_MODEL_FOR_LANGUAGE` and instantiates the analyzer with
    ``supported_languages=[language]`` so the pre-flight in
    :func:`_require_presidio` sees the requested language as registered.

    Raises:
        ImportError: when the ``[ingestion-pii-ml]`` extra is missing —
            the actionable install hint surfaces via
            :func:`_require_presidio` so the operator never sees a deep
            ``OSError`` from spaCy mid-stream.
        ValueError: when ``language`` has no entry in
            :data:`_SPACY_MODEL_FOR_LANGUAGE`. Operators auditing in
            unsupported languages should use ``"xx"`` (multilingual
            fallback) or configure a custom Presidio analyzer
            programmatically.
    """
    if not _HAS_PRESIDIO:
        raise ImportError(_PRESIDIO_INSTALL_HINT)
    if language == "en":
        return _PresidioAnalyzer()
    model_name = _SPACY_MODEL_FOR_LANGUAGE.get(language)
    if model_name is None:
        raise ValueError(
            f"No default spaCy model registered for Presidio language {language!r}. "
            f"Supported language codes: {sorted(_SPACY_MODEL_FOR_LANGUAGE)}. "
            "For other languages, use 'xx' (multilingual fallback, install "
            "'xx_ent_wiki_sm') or configure a custom Presidio AnalyzerEngine "
            "via the Python API (see "
            "https://microsoft.github.io/presidio/analyzer/languages/)."
        )
    # Local import: NlpEngineProvider is part of presidio-analyzer, so
    # gating on ``_HAS_PRESIDIO`` above is sufficient. Importing here
    # rather than at module top keeps the audit module importable when
    # the optional extra is missing.
    from presidio_analyzer.nlp_engine import NlpEngineProvider  # type: ignore[import-not-found]

    nlp_configuration = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": language, "model_name": model_name}],
    }
    nlp_engine = NlpEngineProvider(nlp_configuration=nlp_configuration).create_engine()
    return _PresidioAnalyzer(
        nlp_engine=nlp_engine,
        supported_languages=[language],
    )


# A single, canonical install hint shared by the import-sentinel branch
# and the spaCy-model-missing branch.  Both failure modes look identical
# to the operator (``--pii-ml`` doesn't work; here is the recipe), so
# we keep the message in one place to avoid drift.
_PRESIDIO_INSTALL_HINT: str = (
    "Presidio PII ML detection requires the 'ingestion-pii-ml' extra "
    "AND a spaCy English NER model. Install with:\n"
    "  pip install 'forgelm[ingestion-pii-ml]'\n"
    "  python -m spacy download en_core_web_lg\n"
    "For non-English audits also install the matching spaCy model "
    "(e.g. 'python -m spacy download de_core_news_lg' for --pii-ml-language de)."
)


def _require_presidio(language: str = "en") -> None:
    """Raise a clear ImportError / ValueError when the optional ML-NER backend is unusable.

    Mirrors :func:`_require_datasketch` but extends the check to model
    availability: a fresh ``[ingestion-pii-ml]`` install does **not**
    transitively ship the spaCy NER model — that's a separate
    ``python -m spacy download en_core_web_lg`` step. Without the model
    the first per-row analyzer call would raise ``OSError`` deep inside
    spaCy and (because :func:`detect_pii_ml`'s last-ditch ``except``
    swallows per-row failures) the audit would silently report zero
    ML PII coverage. Pre-flighting the analyzer build here surfaces
    the missing-model case before any rows are scanned.

    When ``language`` is non-default, also verify the requested language
    is registered on the analyzer's supported list. Presidio's default
    ``AnalyzerEngine`` only loads English; ``--pii-ml --pii-ml-language tr``
    against a default install would otherwise return ``{}`` per row
    (``analyzer.analyze`` raises ``ValueError`` which
    :func:`detect_pii_ml` swallows). Failing fast with an actionable
    message is the only way the operator notices the misconfiguration.
    """
    if not _HAS_PRESIDIO:
        raise ImportError(_PRESIDIO_INSTALL_HINT)
    try:
        analyzer = _get_presidio_analyzer(language)
    except OSError as exc:
        # spaCy raises ``OSError`` ("Can't find model 'en_core_web_lg'")
        # when the model package isn't on the import path. Re-raise as
        # ImportError so callers that already catch ImportError for the
        # extras-missing branch see the same exception class for both
        # failure modes.
        _get_presidio_analyzer.cache_clear()
        raise ImportError(
            f"Presidio analyzer build failed (likely missing spaCy NER model for "
            f"language {language!r}): {exc}\n{_PRESIDIO_INSTALL_HINT}"
        ) from exc
    # Defence in depth: ``_get_presidio_analyzer`` builds the analyzer
    # for the requested language so this should always pass, but a stub
    # / mock injected by tests or a future Presidio API change could
    # produce a mismatch — fail loud instead of letting per-row scans
    # silently return ``{}`` when the analyzer doesn't actually support
    # what was asked for.
    supported = getattr(analyzer, "supported_languages", None) or ["en"]
    if language not in supported:
        raise ValueError(
            f"Presidio analyzer has no NLP engine registered for language {language!r}. "
            f"Registered languages: {sorted(supported)}. "
            "Use one of the codes in forgelm.data_audit._SPACY_MODEL_FOR_LANGUAGE, "
            "use 'xx' for the multilingual fallback (install 'xx_ent_wiki_sm'), or "
            "configure a custom Presidio analyzer via the Python API (see "
            "https://microsoft.github.io/presidio/analyzer/languages/)."
        )


# Presidio canonicalises spaCy NER labels through its
# ``model_to_presidio_entity_mapping`` (PER/PERSON → PERSON,
# LOC/GPE → LOCATION, ORG → ORGANIZATION, NORP → NRP); what
# ``analyzer.analyze()`` emits as ``entity_type`` is the canonical
# Presidio name, never the raw spaCy tag. Keep this map keyed on
# canonical Presidio names only so a future maintainer doesn't read
# dead spaCy keys as live coverage.  ``NRP`` (nationality / religious /
# political group) is deliberately not mapped — it's a distinct privacy
# signal from ``location`` and Presidio's NRP precision is too low to
# grade as ``person`` without further work; revisit if compliance
# reviewers ask for it.
_PRESIDIO_ENTITY_MAP: Dict[str, str] = {
    "PERSON": "person",
    "ORGANIZATION": "organization",
    "LOCATION": "location",
}


def detect_pii_ml(text: Any, *, language: str = "en") -> Dict[str, int]:
    """ML-NER PII detector — counts ``person`` / ``organization`` / ``location`` spans.

    Layered ON TOP of :func:`detect_pii` (regex). The two detectors
    return disjoint category sets so the merged ``pii_summary`` shows
    both the structured-identifier signal (regex) and the
    unstructured-identifier signal (ML) without double-counting the
    same span.

    Args:
        text: Per-row payload; defensive against ``None`` / numbers / dicts.
        language: Presidio NLP-engine language code. Default ``"en"``.
            Set via :func:`audit_dataset`'s ``pii_ml_language`` parameter.
            The unsupported-language case is caught up-front by
            :func:`_require_presidio` (called from ``audit_dataset`` when
            ``enable_pii_ml`` is set), so the per-row ``ValueError``
            swallow below only fires for pathological inputs / transient
            engine state, not for misconfiguration.

    Returns an empty dict when:
    * ``text`` is not a non-empty string (defensive — callers pass JSONL
      payloads that may be ``None`` / numbers / dicts);
    * Presidio is not installed (the caller must opt in explicitly via
      :func:`_require_presidio` if they want a hard failure);
    * the analyzer raises a recoverable error on this row — pathological
      strings, transient NLP engine state, language-specific recogniser
      misses. We swallow narrowly-typed failures (``ValueError`` /
      ``RuntimeError``) and let everything else propagate so genuine
      bugs (``OSError`` on missing model, ``MemoryError``, ``KeyboardInterrupt``)
      stay visible. The pre-flight in :func:`_require_presidio` covers
      the missing-model and unsupported-language cases so neither
      reaches this path in the common run.
    """
    if not isinstance(text, str) or not text.strip():
        return {}
    if not _HAS_PRESIDIO:
        return {}
    try:
        analyzer = _get_presidio_analyzer(language)
        results = analyzer.analyze(text=text, language=language)
    except (ValueError, RuntimeError) as exc:  # pragma: no cover — Presidio edge cases
        # Per-row resilience for the narrow class of failures Presidio
        # raises on bad input or transient engine state. ``OSError`` is
        # deliberately NOT caught here — that's the missing-spaCy-model
        # signal and ``_require_presidio``'s pre-flight should have
        # converted it to ImportError before any row was scanned. If
        # one slips through (e.g. lazy model load triggered later),
        # surfacing it loudly is the correct behaviour.
        #
        # Log at DEBUG (not WARNING): per-row failures can fire on
        # every row in pathological corpora, and warning-level spam
        # would drown out the audit's real findings. Operators
        # debugging "why is ML PII coverage zero" can rerun with
        # ``--log-level DEBUG`` to see the per-row exception trail.
        logger.debug(
            "detect_pii_ml: per-row Presidio failure (language=%s): %s",
            language,
            exc,
            exc_info=True,
        )
        return {}
    counts: Dict[str, int] = {}
    for finding in results:
        kind = _PRESIDIO_ENTITY_MAP.get(getattr(finding, "entity_type", ""))
        if kind:
            counts[kind] = counts.get(kind, 0) + 1
    return counts


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
      installed and ``bits == 64`` — non-cryptographic, marginally
      faster on Python (~1.3× raw, ~1.05× end-to-end after the
      ``lru_cache`` below absorbs Zipfian token repeats). Primary
      reason to keep it is forward-compatibility with other simhash
      implementations, not raw throughput.
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


def _compute_simhash_numpy(weights: Dict[str, int], bits: int) -> int:
    """Numpy-vectorised simhash majority vote (dispatched from compute_simhash).

    Builds a (num_unique_tokens × bits) uint8 bit matrix in one shot using
    numpy's right-shift + bitwise-and broadcast, then reduces with a signed
    dot product to get bit_scores without any Python-level loop over bits.
    """
    tokens_list = list(weights.keys())
    w = _np.array([weights[t] for t in tokens_list], dtype=_np.int64)
    hashes = _np.array([_token_digest(t, bits) for t in tokens_list], dtype=_np.uint64)

    # Unpack: shift[i] = hash >> i, then & 1 → (num_tokens, bits) bool matrix
    shifts = _np.arange(bits, dtype=_np.uint64)
    bits_matrix = ((hashes[:, None] >> shifts) & _np.uint64(1)).astype(_np.int8)

    # Signed contribution: +weight where bit=1, -weight where bit=0
    # score[j] = sum_i( w[i] * (2*bit[i,j] - 1) )
    contributions = 2 * bits_matrix - 1  # maps {0,1} → {-1,+1}
    bit_scores = w.astype(_np.int64) @ contributions.astype(_np.int64)  # (bits,)

    # Pack into integer
    set_bits = _np.where(bit_scores > 0)[0]
    if set_bits.size == 0:
        return 0
    return int(sum(1 << int(i) for i in set_bits))


def compute_simhash(text: str, *, bits: int = 64) -> int:
    """64-bit simhash over case-folded word tokens.

    Per-bit majority voting weighted by token frequency, where each
    distinct token's hash is computed once via :func:`_token_digest`
    (cached at module scope). Empty input → ``0``.

    When numpy is available and ``bits`` is a multiple of 8, dispatches to
    :func:`_compute_simhash_numpy` for a ~4–8× speedup on texts with many
    unique tokens.
    """
    tokens = _tokenize(text)
    if not tokens:
        return 0

    weights: Dict[str, int] = {}
    for token in tokens:
        weights[token] = weights.get(token, 0) + 1

    # Numpy fast path uses ``np.uint64`` for the hash dtype, which silently
    # truncates digests wider than 64 bits — fall back to pure Python for
    # those (the hashlib BLAKE2b path scales arbitrarily wide).
    if _HAS_NUMPY and bits % 8 == 0 and bits <= 64:
        return _compute_simhash_numpy(weights, bits)

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


def _bucket_pairs_within_threshold(
    indices: List[int],
    fingerprints: List[int],
    threshold: int,
    seen: set,
) -> List[Tuple[int, int, int]]:
    """Verify the candidate pairs in a single LSH bucket against the full
    Hamming check, deduplicating across buckets via the shared ``seen`` set.
    """
    out: List[Tuple[int, int, int]] = []
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
                out.append((i, j, distance))
    return out


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
    2. Candidates are then verified with the full Hamming distance check
       (see :func:`_bucket_pairs_within_threshold`).

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

    buckets = _build_band_index(fingerprints, bands, bits)
    seen: set = set()
    pairs: List[Tuple[int, int, int]] = []
    for indices in buckets.values():
        if len(indices) < 2:
            continue
        pairs.extend(_bucket_pairs_within_threshold(indices, fingerprints, threshold, seen))

    pairs.sort(key=lambda triple: (triple[0], triple[1]))
    return pairs


# ---------------------------------------------------------------------------
# Phase 12: MinHash LSH near-duplicate detection (optional ``datasketch``)
# ---------------------------------------------------------------------------


def _require_datasketch() -> None:
    """Raise a clear ImportError when the optional MinHash backend is missing."""
    if not _HAS_DATASKETCH:
        raise ImportError(
            "MinHash dedup requires the 'ingestion-scale' extra. Install with: pip install 'forgelm[ingestion-scale]'"
        )


def compute_minhash(text: str, *, num_perm: int = DEFAULT_MINHASH_NUM_PERM) -> Optional[Any]:
    """Build a ``datasketch.MinHash`` from ``text``'s tokenised shingles.

    Returns ``None`` when ``text`` produces no tokens (matches the simhash
    convention of returning ``0`` for empty input — the caller treats both
    sentinels as "skip in pair-walks"). Tokens are the same as
    :func:`_tokenize` (case-folded ``\\w+``); MinHash sees one update per
    **distinct** token (standard MinHash convention).

    Note: this is set-Jaccard similarity over distinct tokens, **not** the
    same metric simhash uses (frequency-weighted bit-cosine over feature
    vectors). The two can disagree on documents with high token-frequency
    variance — e.g. boilerplate / heavy repetition: ``"the cat the cat
    the cat"`` and ``"cat"`` have identical MinHash sketches but distinct
    simhash fingerprints. On natural prose the two methods typically
    agree to within MinHash's permutation noise. Operators that need
    weighted similarity should stick with simhash; MinHash wins when set
    overlap (rather than weighted overlap) is the right notion.
    """
    tokens = _tokenize(text)
    if not tokens:
        return None
    # Lazy: only require the optional extra when we actually need the
    # ``datasketch`` types — defensive callers that call ``compute_minhash("")``
    # still get a clean ``None`` without paying the import cost.
    _require_datasketch()
    m = _MinHash(num_perm=num_perm)
    for token in set(tokens):
        m.update(token.encode("utf-8"))
    return m


def _build_minhash_lsh(
    minhashes: List[Optional[Any]],
    *,
    jaccard_threshold: float,
    num_perm: int,
    key_prefix: str,
) -> Tuple[Any, Dict[str, int]]:
    """Build an LSH index over non-empty MinHashes; return ``(lsh, key→idx)``."""
    lsh = _MinHashLSH(threshold=jaccard_threshold, num_perm=num_perm)
    keys: Dict[str, int] = {}
    for idx, m in enumerate(minhashes):
        if m is None:
            continue
        key = f"{key_prefix}-{idx}"
        keys[key] = idx
        lsh.insert(key, m)
    return lsh, keys


def _emit_minhash_pair(
    idx: int,
    cand_key: str,
    keys: Dict[str, int],
    minhashes: List[Optional[Any]],
    jaccard_threshold: float,
    seen: set,
) -> Optional[Tuple[int, int, float]]:
    """Verify a single LSH candidate; return the pair tuple or ``None``."""
    cand_idx = keys.get(cand_key)
    if cand_idx is None or cand_idx == idx:
        return None
    i, j = (idx, cand_idx) if idx < cand_idx else (cand_idx, idx)
    if (i, j) in seen:
        return None
    seen.add((i, j))
    jaccard = minhashes[i].jaccard(minhashes[j])
    if jaccard < jaccard_threshold:
        return None
    return (i, j, jaccard)


def find_near_duplicates_minhash(
    minhashes: List[Optional[Any]],
    *,
    jaccard_threshold: float = DEFAULT_MINHASH_JACCARD,
    num_perm: int = DEFAULT_MINHASH_NUM_PERM,
) -> List[Tuple[int, int, float]]:
    """Pair-find rows whose MinHash Jaccard similarity ≥ ``jaccard_threshold``.

    Returns ``[(i, j, jaccard), ...]`` with ``i < j``. Mirrors
    :func:`find_near_duplicates`'s shape so the per-split callsite can
    swap one for the other on a method flag.

    Implementation: a single :class:`datasketch.MinHashLSH` index over all
    non-``None`` MinHashes — average-case ``O(n × k)`` where ``k`` is the
    band-bucket fan-out; cluster-collision worst case is still ``O(n²)``
    just like simhash LSH. ``None`` sentinels (empty rows) are skipped
    so they don't pollute the pair set.
    """
    _require_datasketch()
    lsh, keys = _build_minhash_lsh(
        minhashes,
        jaccard_threshold=jaccard_threshold,
        num_perm=num_perm,
        key_prefix="row",
    )

    seen: set = set()
    pairs: List[Tuple[int, int, float]] = []
    for idx, m in enumerate(minhashes):
        if m is None:
            continue
        for cand_key in lsh.query(m):
            triple = _emit_minhash_pair(idx, cand_key, keys, minhashes, jaccard_threshold, seen)
            if triple is not None:
                pairs.append(triple)

    pairs.sort(key=lambda triple: (triple[0], triple[1]))
    return pairs


def _count_leaked_rows_minhash(
    source: List[Optional[Any]],
    target: List[Optional[Any]],
    jaccard_threshold: float,
    *,
    num_perm: int = DEFAULT_MINHASH_NUM_PERM,
) -> int:
    """Rows in ``source`` whose nearest target MinHash has Jaccard ≥ threshold.

    Builds an LSH index over ``target`` once, then queries each non-``None``
    source MinHash. Same shape as :func:`_count_leaked_rows` for simhash —
    drop-in replacement on the ``audit_dataset`` cross-split path.
    """
    # Short-circuit: if every target row is empty (sentinel) there is nothing
    # to compare against. Callers from :func:`_cross_split_overlap` already
    # skip empty splits, but defensive programmatic callers would otherwise
    # pay the LSH-construction cost for a guaranteed-zero result.
    if not any(m is not None for m in target):
        return 0
    _require_datasketch()
    lsh, target_keys = _build_minhash_lsh(
        target,
        jaccard_threshold=jaccard_threshold,
        num_perm=num_perm,
        key_prefix="target",
    )

    leaked = 0
    for m in source:
        if m is None:
            continue
        for cand_key in lsh.query(m):
            cand_idx = target_keys.get(cand_key)
            if cand_idx is None:
                continue
            if m.jaccard(target[cand_idx]) >= jaccard_threshold:
                leaked += 1
                break  # first hit suffices; LSH is candidate-only
    return leaked


def _count_leaks_against_index(
    source_sigs: List[Optional[Any]],
    target_sigs: List[Optional[Any]],
    target_lsh: Any,
    target_keys: Dict[str, int],
    jaccard_threshold: float,
) -> int:
    """Count source rows that have a Jaccard-similar match in the target index.

    Single-direction counterpart used by :func:`_count_leaked_rows_minhash_bidirectional`.
    Each source signature is queried against the target's pre-built LSH; the
    first candidate whose actual Jaccard ≥ threshold is enough to flag a leak,
    so we ``break`` after the first hit.
    """
    leaked = 0
    for m in source_sigs:
        if m is None:
            continue
        for cand_key in target_lsh.query(m):
            cand_idx = target_keys.get(cand_key)
            if cand_idx is None:
                continue
            if m.jaccard(target_sigs[cand_idx]) >= jaccard_threshold:
                leaked += 1
                break
    return leaked


def _count_leaked_rows_minhash_bidirectional(
    sigs_a: List[Optional[Any]],
    sigs_b: List[Optional[Any]],
    jaccard_threshold: float,
    *,
    num_perm: int = DEFAULT_MINHASH_NUM_PERM,
) -> Tuple[int, int]:
    """Both-directional MinHash leak counts; builds each LSH index exactly once.

    Previous callers invoked :func:`_count_leaked_rows_minhash` twice — once
    with (a, b) and once with (b, a) — which built LSH(b) and LSH(a) as
    separate calls, paying the construction cost 2× per direction pair.
    This function builds each index once and reuses it for both queries,
    halving the dominant ``O(n_b × bands)`` / ``O(n_a × bands)`` cost.
    """
    has_a = any(m is not None for m in sigs_a)
    has_b = any(m is not None for m in sigs_b)
    if not has_a or not has_b:
        return 0, 0
    _require_datasketch()

    lsh_a, keys_a = _build_minhash_lsh(sigs_a, jaccard_threshold=jaccard_threshold, num_perm=num_perm, key_prefix="a")
    lsh_b, keys_b = _build_minhash_lsh(sigs_b, jaccard_threshold=jaccard_threshold, num_perm=num_perm, key_prefix="b")

    leaked_a = _count_leaks_against_index(sigs_a, sigs_b, lsh_b, keys_b, jaccard_threshold)
    leaked_b = _count_leaks_against_index(sigs_b, sigs_a, lsh_a, keys_a, jaccard_threshold)
    return leaked_a, leaked_b


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


# ---------------------------------------------------------------------------
# Streaming length digest — bounded memory for large corpora (C.2)
# ---------------------------------------------------------------------------

# Reservoir size: below this the digest is exact; above it p50/p95 are
# approximate via Algorithm R random sampling. 100K ints ≈ 800 KB — a
# negligible fraction of peak audit memory even on multi-million-row splits.
_LENGTH_RESERVOIR_SIZE = 100_000


class _LengthDigest:
    """Streaming min/max/mean/p50/p95 accumulator with bounded memory.

    Replaces the ``text_lengths: List[int]`` field on ``_StreamingAggregator``,
    which grew O(n) — 80 MB+ per split on 10 M-row corpora.  This keeps
    memory capped at ``_LENGTH_RESERVOIR_SIZE`` integers (≈ 800 KB) regardless
    of dataset size; p50/p95 are exact up to that cap, approximate beyond it.
    """

    __slots__ = ("_n", "_total", "_min", "_max", "_reservoir", "_rng_counter")

    def __init__(self) -> None:
        self._n: int = 0
        self._total: int = 0
        self._min: int = 0
        self._max: int = 0
        self._reservoir: List[int] = []
        # Inline LCG counter for reservoir sampling — avoids importing random
        # and keeps the digest deterministic when seeded externally.
        self._rng_counter: int = 0

    def update(self, length: int) -> None:
        self._n += 1
        self._total += length
        if self._n == 1:
            self._min = self._max = length
        else:
            if length < self._min:
                self._min = length
            if length > self._max:
                self._max = length
        if len(self._reservoir) < _LENGTH_RESERVOIR_SIZE:
            self._reservoir.append(length)
        else:
            # Algorithm R: replace a random slot with decreasing probability
            # Use a simple LCG for speed and to avoid global random state.
            self._rng_counter = (self._rng_counter * 6364136223846793005 + 1) & 0xFFFFFFFFFFFFFFFF
            j = self._rng_counter % self._n
            if j < _LENGTH_RESERVOIR_SIZE:
                self._reservoir[j] = length

    def stats(self) -> Dict[str, float]:
        if self._n == 0:
            return {}
        s = sorted(self._reservoir)
        k = len(s)
        return {
            "min": self._min,
            "max": self._max,
            "mean": round(self._total / self._n, 1),
            "p50": s[k // 2],
            "p95": s[min(k - 1, int(k * 0.95))],
        }


# ---------------------------------------------------------------------------
# Phase 12: code/secrets leakage tagger
# ---------------------------------------------------------------------------


# Fallback regex set used when ``detect-secrets`` is not installed. Keep
# patterns narrow — false positives in this category waste the operator's
# attention and (more importantly) erode trust in the audit. Each pattern
# is anchored on the canonical prefix the secret format publishes; we do
# NOT try to match generic high-entropy strings here because ``detect-secrets``
# does that better and we'd rather guide the operator to the extra than
# pretend we cover it.
SECRET_TYPES: Tuple[str, ...] = (
    "aws_access_key",
    "github_token",
    "slack_token",
    "openai_api_key",
    "google_api_key",
    "jwt",
    "openssh_private_key",
    "pgp_private_key",
    "azure_storage_key",
)


_SECRET_PATTERNS: Dict[str, re.Pattern] = {
    # AWS access key IDs follow AKIA / ASIA + 16 uppercase alphanum.
    "aws_access_key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    # GitHub fine-grained / classic PAT prefixes (see GitHub token-format docs).
    # ``re.ASCII`` because GitHub tokens are strictly ASCII — Python's default
    # ``\w`` is Unicode-aware, which would otherwise let non-ASCII chars leak
    # into the match universe (regex.md rule 1).
    "github_token": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat)_\w{20,}", flags=re.ASCII),
    # Slack bot / user / app / config tokens.
    "slack_token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    # OpenAI API keys (legacy ``sk-…`` and project-scoped ``sk-proj-…``).
    # ``[\w-]`` + ``re.ASCII`` keeps ``\w`` ASCII-bounded.
    "openai_api_key": re.compile(r"\bsk-(?:proj-)?[\w-]{20,}\b", flags=re.ASCII),
    # Google API keys (Maps, Cloud, etc.).
    "google_api_key": re.compile(r"\bAIza[\w-]{35}\b", flags=re.ASCII),
    # JSON Web Tokens — header.payload.sig. We anchor the header segment
    # on the base64url prefix of the canonical JWT header keys (``alg`` /
    # ``typ`` / ``kid`` / ``cty`` / ``enc``) and require minimum lengths
    # on payload + signature, so generic ``eyJ.eyJ.X``-shaped strings in
    # prose don't false-positive. This still catches >99 % of real JWTs.
    # ``re.ASCII`` because base64url is ASCII-only.
    "jwt": re.compile(
        r"\beyJ(?:hbGc|0eXA|raWQ|jdHk|lbmM|hcGk)[\w-]{10,}"
        r"\.eyJ[\w-]{10,}"
        r"\.[\w-]{15,}\b",
        flags=re.ASCII,
    ),
    # Private-key blocks — full PEM/PGP envelope (BEGIN through END inclusive)
    # so ``mask_secrets`` redacts the entire block, not just the header line.
    # The literal block markers below are spelled with concatenation to keep
    # naive secret-scanners on the source tree from misreading the regex
    # itself as a leaked private key.
    "openssh_private_key": re.compile(
        r"-----" + r"BEGIN " + r"(?:OPENSSH|RSA|DSA|EC) PRIVATE KEY-----"
        r".*?"
        r"-----" + r"END " + r"(?:OPENSSH|RSA|DSA|EC) PRIVATE KEY-----",
        re.DOTALL,
    ),
    "pgp_private_key": re.compile(
        r"-----" + r"BEGIN " + r"PGP PRIVATE KEY BLOCK-----"
        r".*?"
        r"-----" + r"END " + r"PGP PRIVATE KEY BLOCK-----",
        re.DOTALL,
    ),
    # Azure storage account keys are 88-char base64; we narrow on the
    # common ``DefaultEndpointsProtocol`` connection-string context.
    "azure_storage_key": re.compile(
        r"DefaultEndpointsProtocol=https?;AccountName=[A-Za-z0-9]+;AccountKey=[A-Za-z0-9+/=]{20,}"
    ),
}


def detect_secrets(text: Any) -> Dict[str, int]:
    """Return ``{secret_type: count}`` for credentials/keys leaked in ``text``.

    Uses :data:`_SECRET_PATTERNS` (anchored regexes) by default. The
    optional ``detect-secrets`` extra is **not** invoked here because its
    scanning model assumes file paths; ingest's per-chunk text wouldn't
    benefit. The audit calls this once per row payload; the regex set is
    intentionally narrow (prefix-anchored) to keep false positives low.
    """
    counts: Dict[str, int] = {}
    if not text or not isinstance(text, str):
        return counts
    for kind, pattern in _SECRET_PATTERNS.items():
        hits = pattern.findall(text)
        if hits:
            counts[kind] = len(hits)
    return counts


def mask_secrets(
    text: Any,
    replacement: str = "[REDACTED-SECRET]",
    *,
    return_counts: bool = False,
) -> Any:
    """Return ``text`` with detected secret spans replaced by ``replacement``.

    Mirrors :func:`mask_pii`'s API surface (``return_counts`` for the
    truthful per-type tally). Non-string input passes through. Used by
    ``forgelm ingest --secrets-mask`` to scrub credentials before chunks
    land in the JSONL — fine-tuning a model on a corpus that includes
    real API keys causes them to be memorised at training time.
    """
    if not text or not isinstance(text, str):
        return (text, {}) if return_counts else text
    counts: Dict[str, int] = {}
    out = text
    for kind, pattern in _SECRET_PATTERNS.items():

        def _replace(match: re.Match, _t: str = kind) -> str:
            counts[_t] = counts.get(_t, 0) + 1
            return replacement

        out = pattern.sub(_replace, out)
    return (out, counts) if return_counts else out


# ---------------------------------------------------------------------------
# Phase 12: heuristic quality filter (audit-side, opt-in)
# ---------------------------------------------------------------------------


_QUALITY_CHECKS: Tuple[str, ...] = (
    "low_alpha_ratio",
    "low_punct_endings",
    "abnormal_mean_word_length",
    "short_paragraphs",
    "repeated_lines",
)
"""Per-row quality-heuristic identifiers. Same names land in the audit
JSON's ``quality_summary.by_check`` map; tests pin them so a future
addition / rename doesn't silently break consumers."""


_WORD_PATTERN = re.compile(r"\b[\w']+\b", re.UNICODE)
# ``[ \t]*$`` not ``\s*$``: callers pass single lines (no embedded
# newlines), so the ``\s`` form's newline-overlap potential is dead
# weight per docs/standards/regex.md rule 5.
_PUNCT_END_PATTERN = re.compile(r"[.!?…\"'\)\]][ \t]*$")


def _is_code_fence_open(line: str) -> Optional[Tuple[str, int]]:
    """Return ``(fence_char, run_length)`` if ``line`` opens a CommonMark fence, else ``None``.

    CommonMark §4.5: an opening fence is 3+ identical backticks (or
    tildes), optionally indented by up to 3 spaces, possibly followed by
    an info string. We capture the **run length** because a valid
    closing fence must use at least as many fence characters as the
    opener — a 4-backtick block is *not* closed by a 3-backtick line.
    """
    stripped = line.lstrip(" ")
    if len(line) - len(stripped) > 3:
        return None  # 4+ spaces: indented code block, not a fence
    if stripped.startswith("```"):
        run = len(stripped) - len(stripped.lstrip("`"))
        # CommonMark §4.5: the info string after a backtick fence may not
        # contain backticks. Lines like ``` ```lang `oops`` are *not*
        # opening fences — treating them as one would mis-parse inline
        # code in prose as a code block.
        rest = stripped[run:]
        if "`" in rest:
            return None
        return ("`", run)
    if stripped.startswith("~~~"):
        run = len(stripped) - len(stripped.lstrip("~"))
        return ("~", run)
    return None


def _is_code_fence_close(line: str, fence_char: str, min_run: int) -> bool:
    """Return ``True`` when ``line`` is a valid CommonMark close for ``(fence_char, min_run)``.

    Stricter than ``_is_code_fence_open``:

    1. The closing fence may **not** carry an info string — only the
       fence run + optional trailing whitespace. ``~~~bash`` opens a
       tilde block but does **not** close one.
    2. Per CommonMark §4.5, the close must use **at least as many**
       fence characters as the opener, so a ``\\`\\`\\``\\``` block
       (4 backticks) is not closed by a ``\\`\\`\\``` line (3 backticks).
    """
    stripped = line.lstrip(" ")
    if len(line) - len(stripped) > 3:
        return False
    body = stripped.rstrip(" \t\r\n")
    if len(body) < min_run:
        return False
    return all(ch == fence_char for ch in body)


def _strip_code_fences(text: str) -> str:
    """Remove CommonMark fenced code blocks (``\\`\\`\\``` or ``~~~``); leave inline code intact.

    Implemented as a per-line state machine rather than a single regex
    so the cost is provably O(n). The previous regex
    ``^ {0,3}(?P<fence>\\`{3,}|~{3,})[^\\n]*\\n.*?^ {0,3}(?P=fence)[ \\t]*$``
    used ``.*?`` with a back-reference under DOTALL, which static
    analysers (SonarCloud python:S5852) flag as a polynomial-runtime
    risk — and the same line-walker pattern is already used in
    :func:`forgelm.ingestion._markdown_sections`, so we use it here too.

    Tracks the **opening fence char + run length** per CommonMark §4.5
    so a 4-backtick opener isn't prematurely closed by a 3-backtick line.
    Behaviour matches the old regex bit-for-bit on the standard test
    fixtures: a fully-closed fence is replaced by the surrounding line
    breaks (``intro\\n…block…\\nouter`` → ``intro\\n\\nouter``); an
    *unclosed* fence is left untouched.
    """
    out: List[str] = []
    open_fence: Optional[Tuple[str, int]] = None  # (char, min_close_length) while in block
    block_buffer: List[str] = []  # accumulates an in-progress block

    for line in text.splitlines(keepends=True):
        if open_fence is None:
            fence_info = _is_code_fence_open(line)
            if fence_info is not None:
                open_fence = fence_info
                block_buffer = [line]  # buffer in case the block is unclosed
            else:
                out.append(line)
            continue
        # Inside an active block: buffer the line, then check for close.
        block_buffer.append(line)
        fence_char, min_run = open_fence
        if _is_code_fence_close(line, fence_char, min_run):
            # The regex consumed BEGIN through CLOSE inclusive but stopped
            # before the trailing ``\n`` — preserve that newline so the
            # surrounding lines aren't glued together.
            if block_buffer[-1].endswith("\n"):
                out.append("\n")
            block_buffer = []
            open_fence = None

    # Unclosed block: flush the buffered lines back to output verbatim
    # (the old regex would have failed to match a partial block, so the
    # surrounding text stayed as-is).
    if block_buffer:
        out.extend(block_buffer)

    return "".join(out)


def _check_low_alpha_ratio(prose: str) -> Optional[str]:
    """Flag prose whose letter-to-non-whitespace ratio falls below 70 %."""
    non_ws = [c for c in prose if not c.isspace()]
    if not non_ws:
        return None
    alpha_ratio = sum(1 for c in non_ws if c.isalpha()) / len(non_ws)
    return "low_alpha_ratio" if alpha_ratio < 0.70 else None


def _check_low_punct_endings(lines: List[str]) -> Optional[str]:
    """Flag when fewer than 50 % of non-empty lines end with punctuation."""
    if not lines:
        return None
    punct_ratio = sum(1 for ln in lines if _PUNCT_END_PATTERN.search(ln)) / len(lines)
    return "low_punct_endings" if punct_ratio < 0.50 else None


def _check_abnormal_mean_word_length(words: List[str]) -> Optional[str]:
    """Flag mean word length outside the 3-12 char window."""
    mean_wl = sum(len(w) for w in words) / len(words)
    return "abnormal_mean_word_length" if mean_wl < 3.0 or mean_wl > 12.0 else None


def _check_short_paragraphs(prose: str) -> Optional[str]:
    """Flag when > 50 % of ``\\n\\n``-blocks contain < 5 words."""
    paragraphs = [p for p in prose.split("\n\n") if p.strip()]
    if not paragraphs:
        return None
    short = sum(1 for p in paragraphs if len(_WORD_PATTERN.findall(p)) < 5)
    return "short_paragraphs" if short / len(paragraphs) > 0.50 else None


def _check_repeated_lines(lines: List[str]) -> Optional[str]:
    """Flag when the top-3 *actually-repeating* lines (count ≥ 2) cover > 30 %.

    A naive "top-3 distinct lines" rule fires on any short all-unique
    document; pinning on count ≥ 2 isolates real boilerplate (repeated
    headers / footers / disclaimers).
    """
    if len(lines) < 3:
        return None
    line_counts = Counter(lines)
    repeating = [(ln, n) for ln, n in line_counts.items() if n >= 2]
    if not repeating:
        return None
    repeating.sort(key=lambda kv: kv[1], reverse=True)
    top3_total = sum(n for _, n in repeating[:3])
    return "repeated_lines" if top3_total / len(lines) > 0.30 else None


def _row_quality_flags(text: Optional[str]) -> List[str]:
    """Return the subset of :data:`_QUALITY_CHECKS` that flag ``text``.

    Heuristics are intentionally conservative (Gopher / C4 / RefinedWeb
    style — none of them block training; they surface in the audit so the
    operator decides whether to filter). Empty / non-string input
    short-circuits with an empty list so :class:`_StreamingAggregator`
    can call this on every row without per-call type checks.

    Fenced markdown code blocks (``` … ``` or ``~~~ … ~~~``) are stripped
    before applying prose heuristics — code is legitimate SFT content but
    trips ``low_alpha_ratio`` / ``low_punct_endings`` / ``short_paragraphs``
    on its own. If the row is **purely** code (nothing left after
    stripping), the function returns ``[]`` rather than flagging the
    whole row.
    """
    if not isinstance(text, str) or not text.strip():
        return []
    prose = _strip_code_fences(text).strip()
    if not prose:
        # Pure code-fence rows: don't flag — this is legitimate SFT data
        # for code-instruction models, not noise.
        return []
    words = _WORD_PATTERN.findall(prose)
    if not words:
        return ["low_alpha_ratio"]
    lines = [ln for ln in prose.splitlines() if ln.strip()]

    # Each helper returns either a flag name or ``None``; collect the hits.
    candidates = [
        _check_low_alpha_ratio(prose),
        _check_low_punct_endings(lines),
        _check_abnormal_mean_word_length(words),
        _check_short_paragraphs(prose),
        _check_repeated_lines(lines),
    ]
    return [flag for flag in candidates if flag is not None]


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

    Phase 12 additions:

    * ``dedup_method`` selects simhash (default; populates ``fingerprints``)
      vs. MinHash (populates ``minhashes``). Only one is computed per row
      so we don't pay the other method's cost.
    * ``secrets_counts`` aggregates :func:`detect_secrets` hits across rows.
      Always scanned — credentials are never opt-in.
    * ``quality_flags_counts`` aggregates :func:`_row_quality_flags` hits
      when ``enable_quality_filter`` is True (opt-in via CLI flag).
    """

    sample_count: int = 0
    parse_errors: int = 0
    decode_errors: int = 0
    non_object_rows: int = 0
    null_or_empty: int = 0
    # Phase 11.5: keep a Counter of distinct keysets rather than appending
    # one frozenset per row. On a 1 M-row split with stable schema this is
    # 1 entry vs. 1 M identical frozensets — the .most_common(1) lookup at
    # finalisation time is unchanged.
    keyset_counts: "Counter[frozenset]" = field(default_factory=Counter)
    seen_columns: "OrderedDict[str, None]" = field(default_factory=OrderedDict)
    length_digest: _LengthDigest = field(default_factory=_LengthDigest)
    fingerprints: List[int] = field(default_factory=list)
    minhashes: List[Optional[Any]] = field(default_factory=list)
    pii_counts: Dict[str, int] = field(default_factory=dict)
    secrets_counts: Dict[str, int] = field(default_factory=dict)
    quality_flags_counts: Dict[str, int] = field(default_factory=dict)
    quality_samples_flagged: int = 0
    quality_samples_evaluated: int = 0  # rows that actually went through _row_quality_flags
    lang_sample: List[str] = field(default_factory=list)
    # Phase 12 configuration (set once by the orchestrator; never mutated).
    dedup_method: str = "simhash"
    minhash_num_perm: int = DEFAULT_MINHASH_NUM_PERM
    # Phase 12.5: opt-in ML-NER PII detection (Presidio). Off by default.
    enable_pii_ml: bool = False
    pii_ml_language: str = "en"
    enable_quality_filter: bool = False


def _record_schema_for_dict(agg: _StreamingAggregator, row: Dict[str, Any]) -> None:
    keys = frozenset(row.keys())
    agg.keyset_counts[keys] += 1
    for col in keys:
        agg.seen_columns.setdefault(col, None)


def _record_dedup_signature(agg: _StreamingAggregator, payload: str) -> None:
    """Compute the per-row dedup signature for the aggregator's selected method.

    Only one of ``fingerprints`` / ``minhashes`` is populated per row —
    paying both costs would defeat the point of method selection. The
    sentinel for "skip in pair-walks" differs by method: simhash uses
    integer ``0`` (cheap to test); minhash uses ``None``.
    """
    if agg.dedup_method == "minhash":
        agg.minhashes.append(compute_minhash(payload, num_perm=agg.minhash_num_perm))
    else:
        agg.fingerprints.append(compute_simhash(payload))


def _record_dedup_sentinel(agg: _StreamingAggregator) -> None:
    """Append the empty-row sentinel for whichever dedup method is active."""
    if agg.dedup_method == "minhash":
        agg.minhashes.append(None)
    else:
        agg.fingerprints.append(0)


def _record_text_metrics(agg: _StreamingAggregator, payload: str) -> None:
    agg.length_digest.update(len(payload))
    if len(agg.lang_sample) < _LANG_SAMPLE_SIZE:
        agg.lang_sample.append(payload)
    _record_dedup_signature(agg, payload)
    for kind, count in detect_pii(payload).items():
        agg.pii_counts[kind] = agg.pii_counts.get(kind, 0) + count
    if agg.enable_pii_ml:
        # Phase 12.5: Presidio NER findings layer onto the same pii_counts
        # bucket. The category names are disjoint from the regex set
        # (person / organization / location vs. email / phone / *_id),
        # so the merged counts present both views without double-counting.
        # ``pii_ml_language`` is plumbed through so a Turkish-majority
        # corpus can be audited with a Turkish spaCy model rather than
        # silently scoring zero NER findings under English.
        for kind, count in detect_pii_ml(payload, language=agg.pii_ml_language).items():
            agg.pii_counts[kind] = agg.pii_counts.get(kind, 0) + count
    for kind, count in detect_secrets(payload).items():
        agg.secrets_counts[kind] = agg.secrets_counts.get(kind, 0) + count
    if agg.enable_quality_filter:
        # Count this row as "evaluated" — the denominator in
        # ``overall_quality_score`` must reflect rows that actually went
        # through ``_row_quality_flags``, not the full sample count
        # (null/non-dict rows skip this branch and would otherwise
        # depress the score).
        agg.quality_samples_evaluated += 1
        flags = _row_quality_flags(payload)
        if flags:
            agg.quality_samples_flagged += 1
            for flag in flags:
                agg.quality_flags_counts[flag] = agg.quality_flags_counts.get(flag, 0) + 1


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
        # cannot extract anything useful. We flag them as ``non_object_rows``
        # (sharp shape-problem signal — distinct from "row had a text column
        # but it was empty") AND bump ``null_or_empty`` so downstream length
        # stats and the null_or_empty_rate treat them as unusable rows. Without
        # the null_or_empty bump, null_or_empty_rate would silently understate
        # corruption while length stats / fingerprints excluded them. The
        # sentinel ``0`` fingerprint (or ``None`` minhash) here keeps the
        # signature index aligned with row indices so within/cross-split LSH
        # walks skip them cleanly. Tested at
        # tests/test_data_audit.py::TestNonDictRowTolerance.
        agg.non_object_rows += 1
        agg.null_or_empty += 1
        _record_dedup_sentinel(agg)
        return

    _record_schema_for_dict(agg, row)
    payload = _extract_text_payload(row)
    if not payload:
        agg.null_or_empty += 1
        _record_dedup_sentinel(agg)
        return
    _record_text_metrics(agg, payload)


def _populate_schema_block(info: Dict[str, Any], agg: _StreamingAggregator) -> None:
    """Fill columns / schema-drift / non-object-row fields on ``info``."""
    columns_list = list(agg.seen_columns)
    if columns_list:
        info["columns"] = columns_list
    if agg.keyset_counts:
        most_common_keyset, _ = agg.keyset_counts.most_common(1)[0]
        base_columns = set(most_common_keyset)
        drift_columns = [c for c in columns_list if c not in base_columns]
        if drift_columns:
            info["schema_drift_columns"] = drift_columns
    if agg.non_object_rows:
        info["non_object_rows"] = agg.non_object_rows


def _populate_optional_findings(info: Dict[str, Any], agg: _StreamingAggregator) -> None:
    """Fill PII / secrets / quality blocks on ``info`` (only when non-empty)."""
    if agg.pii_counts:
        info["pii_counts"] = dict(agg.pii_counts)
    if agg.secrets_counts:
        info["secrets_counts"] = dict(agg.secrets_counts)
    if agg.enable_quality_filter and agg.quality_flags_counts:
        info["quality_flags_counts"] = dict(agg.quality_flags_counts)
        info["quality_samples_flagged"] = agg.quality_samples_flagged
        info["quality_samples_evaluated"] = agg.quality_samples_evaluated


def _within_split_pairs(
    agg: _StreamingAggregator,
    *,
    near_dup_threshold: int,
    minhash_jaccard: float,
) -> int:
    """Run the within-split near-duplicate scan, dispatching on dedup method."""
    if agg.dedup_method == "minhash":
        pairs = find_near_duplicates_minhash(
            agg.minhashes,
            jaccard_threshold=minhash_jaccard,
            num_perm=agg.minhash_num_perm,
        )
    else:
        pairs = find_near_duplicates(agg.fingerprints, threshold=near_dup_threshold)
    return len(pairs)


def _aggregator_to_info(
    split_name: str,
    agg: _StreamingAggregator,
    *,
    near_dup_threshold: int,
    minhash_jaccard: float = DEFAULT_MINHASH_JACCARD,
) -> Dict[str, Any]:
    """Render the aggregator state as the per-split ``info`` payload."""
    info: Dict[str, Any] = {"sample_count": agg.sample_count}
    if agg.sample_count == 0:
        info["near_duplicate_pairs"] = 0
        return info

    _populate_schema_block(info, agg)

    length_stats = agg.length_digest.stats()
    if length_stats:
        info["text_length"] = length_stats
    info["null_or_empty_count"] = agg.null_or_empty
    info["null_or_empty_rate"] = round(agg.null_or_empty / agg.sample_count, 4)

    languages_top3 = _compute_top_languages(agg.lang_sample)
    if languages_top3:
        info["languages_top3"] = languages_top3

    if agg.dedup_method == "minhash":
        # Mirror simhash_distinct's semantic: count *unique* sketches, not
        # just the number of non-empty rows. ``hashvalues.tobytes()`` gives
        # a hashable, memory-efficient fingerprint of each MinHash state.
        info["minhash_distinct"] = len({m.hashvalues.tobytes() for m in agg.minhashes if m is not None})
    else:
        info["simhash_distinct"] = len({fp for fp in agg.fingerprints if fp != 0})

    _populate_optional_findings(info, agg)

    if agg.sample_count >= _PROGRESS_INTERVAL:
        logger.info(
            "audit/%s: scanning for near-duplicates (%s; %d rows)…",
            split_name,
            "MinHash LSH" if agg.dedup_method == "minhash" else "simhash LSH-banded",
            agg.sample_count,
        )
    info["near_duplicate_pairs"] = _within_split_pairs(
        agg,
        near_dup_threshold=near_dup_threshold,
        minhash_jaccard=minhash_jaccard,
    )
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
    dedup_method: str = "simhash",
    minhash_jaccard: float = DEFAULT_MINHASH_JACCARD,
    minhash_num_perm: int = DEFAULT_MINHASH_NUM_PERM,
    enable_quality_filter: bool = False,
    enable_pii_ml: bool = False,
    pii_ml_language: str = "en",
) -> Tuple[Dict[str, Any], List[Any], Dict[str, int], int, int]:
    """Stream a JSONL split into a metrics record.

    Phase 11.5 streamed this end-to-end: the function consumes
    :func:`_read_jsonl_split` row-by-row and folds each line straight
    into a :class:`_StreamingAggregator`. Memory is dominated by:

    * the per-row dedup signature list (``fingerprints`` for simhash, ~28 B/row;
      ``minhashes`` for MinHash, ~1-2 KB/row at ``num_perm=128``)
    * the per-row text-length list — same order of magnitude as fingerprints
    * a fixed-size language sample (200 strings)
    * a :class:`Counter` of distinct keysets (typically O(1) entries when
      schema is stable; only grows with genuine schema drift)

    Phase 12 adds the ``dedup_method`` switch (default ``"simhash"``;
    ``"minhash"`` opts into LSH-banded MinHash via the ``ingestion-scale``
    extra), the always-on secrets scan (no flag), and the opt-in quality
    filter (``enable_quality_filter``).

    Compared to the pre-Phase-11.5 buffered path that kept every parsed
    row + every text payload string in RAM (hundreds of MB on 100 K rows
    of 4 KB text), this is a large absolute reduction — but it is **not**
    constant memory, because the signature and length lists still grow
    linearly in row count. Operators that need true bounded RAM on
    truly huge splits should sample first.

    Returns:
        ``(info_dict, signatures, pii_counts, parse_errors, decode_errors)``
        — ``signatures`` is the per-row simhash int list when method is
        ``"simhash"`` and the per-row MinHash list when method is
        ``"minhash"``. Caller (:func:`_process_split`) feeds it back into
        the cross-split overlap path which dispatches on the same method.
    """
    agg = _StreamingAggregator(
        dedup_method=dedup_method,
        minhash_num_perm=minhash_num_perm,
        enable_quality_filter=enable_quality_filter,
        enable_pii_ml=enable_pii_ml,
        pii_ml_language=pii_ml_language,
    )
    for row, parse_err, decode_err in _read_jsonl_split(path):
        _ingest_row(agg, row, parse_err, decode_err)
        if agg.sample_count and agg.sample_count % _PROGRESS_INTERVAL == 0:
            logger.info(
                "audit/%s: %d rows scanned (streaming)…",
                split_name,
                agg.sample_count,
            )

    info = _aggregator_to_info(
        split_name,
        agg,
        near_dup_threshold=near_dup_threshold,
        minhash_jaccard=minhash_jaccard,
    )
    # Pass the aggregator's lists by reference instead of materialising a
    # copy. The downstream cross-split overlap (`_cross_split_pairs`)
    # already produces a new filtered list (`[m for m in sigs if m is not
    # None]`) before walking, so this signature list is never mutated by
    # consumers. The previous `list(agg.minhashes)` defensive copy doubled
    # peak memory on a 1M-row split (≈1-2 KB per MinHash sketch × 1M ×
    # 2 = ~2.5 GB resident before LSH even started).
    signatures: List[Any] = agg.minhashes if dedup_method == "minhash" else agg.fingerprints
    return info, signatures, dict(agg.pii_counts), agg.parse_errors, agg.decode_errors


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


def _count_leaked_brute(source: List[int], target: List[int], threshold: int) -> int:
    """Linear-scan fallback used when LSH banding cannot be configured."""
    return sum(
        1
        for fp in source
        if fp != 0 and any(other != 0 and hamming_distance(fp, other) <= threshold for other in target)
    )


def _source_row_leaks(
    fp: int,
    target_index: Dict[Tuple[int, int], List[int]],
    target: List[int],
    threshold: int,
    bands: int,
    bits: int,
) -> bool:
    """Walk one source row's bands; return True on the first target hit.

    The ``seen`` set is per-source-row: we never double-check the same
    target index across the source row's bands, but a fresh source row
    starts with an empty ``seen`` because its hits are independent.
    """
    seen: set = set()
    for band_idx, band_val in enumerate(_split_into_bands(fp, bands, bits)):
        candidates = target_index.get((band_idx, band_val))
        if not candidates:
            continue
        for j in candidates:
            if j in seen:
                continue
            seen.add(j)
            if hamming_distance(fp, target[j]) <= threshold:
                return True
    return False


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
    longer needs the full ``100K × 10K`` Hamming sweep. Falls back to
    :func:`_count_leaked_brute` when banding cannot be configured (edge
    thresholds where bands shrink below 4 bits).
    """
    bands = _band_count_for_threshold(threshold, bits)
    if bands == 0:
        return _count_leaked_brute(source, target, threshold)

    target_index = _build_band_index(target, bands, bits)
    if not target_index:
        return 0

    return sum(1 for fp in source if fp != 0 and _source_row_leaks(fp, target_index, target, threshold, bands, bits))


def _pair_leak_payload(
    a: str,
    sigs_a: List[Any],
    b: str,
    sigs_b: List[Any],
    *,
    dedup_method: str,
    threshold: int,
    minhash_jaccard: float,
    minhash_num_perm: int,
) -> Dict[str, Any]:
    """Both-directional leak counts + rates for one (a, b) split pair.

    Dispatches on ``dedup_method``: simhash uses Hamming-distance LSH;
    minhash uses Jaccard-similarity LSH (datasketch). Same shape on
    both paths so consumers can read ``leak_rate_<split>`` without
    knowing which method ran.
    """
    if dedup_method == "minhash":
        leaked_in_a, leaked_in_b = _count_leaked_rows_minhash_bidirectional(
            sigs_a, sigs_b, minhash_jaccard, num_perm=minhash_num_perm
        )
    else:
        leaked_in_a = _count_leaked_rows(sigs_a, sigs_b, threshold)
        leaked_in_b = _count_leaked_rows(sigs_b, sigs_a, threshold)
    return {
        f"leaked_rows_in_{a}": leaked_in_a,
        f"leak_rate_{a}": round(leaked_in_a / len(sigs_a), 4),
        f"leaked_rows_in_{b}": leaked_in_b,
        f"leak_rate_{b}": round(leaked_in_b / len(sigs_b), 4),
    }


def _cross_split_overlap(
    signatures_by_split: Dict[str, List[Any]],
    *,
    dedup_method: str,
    threshold: int,
    minhash_jaccard: float = DEFAULT_MINHASH_JACCARD,
    minhash_num_perm: int = DEFAULT_MINHASH_NUM_PERM,
) -> Dict[str, Any]:
    """Pairwise leakage report across train/validation/test splits.

    Reports leak rate **in both directions** — the symmetric ratio
    (shared / smaller-split-size) is the metric that actually destroys
    benchmark fidelity, but the asymmetric one (shared / larger split)
    is informative too. Without both, an operator scanning
    ``train__test = 0.05`` could miss that the same 5 rows leak 50% of
    a small test set.

    ``signatures_by_split`` carries simhash ints (when method is
    ``"simhash"``) or :class:`datasketch.MinHash` instances (method is
    ``"minhash"``). Sentinel filtering matches the per-method scheme:
    ``0`` for simhash, ``None`` for minhash.
    """
    if dedup_method == "minhash":
        nonempty = {name: [m for m in sigs if m is not None] for name, sigs in signatures_by_split.items()}
        report: Dict[str, Any] = {
            "method": "minhash",
            "jaccard_threshold": minhash_jaccard,
            "num_perm": minhash_num_perm,
            "pairs": {},
        }
    else:
        nonempty = {name: [fp for fp in sigs if fp != 0] for name, sigs in signatures_by_split.items()}
        report = {"method": "simhash", "hamming_threshold": threshold, "pairs": {}}

    splits = list(nonempty.keys())
    for i, a in enumerate(splits):
        sigs_a = nonempty[a]
        if not sigs_a:
            continue
        for j in range(i + 1, len(splits)):
            b = splits[j]
            sigs_b = nonempty[b]
            if not sigs_b:
                continue
            report["pairs"][f"{a}__{b}"] = _pair_leak_payload(
                a,
                sigs_a,
                b,
                sigs_b,
                dedup_method=dedup_method,
                threshold=threshold,
                minhash_jaccard=minhash_jaccard,
                minhash_num_perm=minhash_num_perm,
            )
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
    """Bundle of per-split results assembled by :func:`_process_split`.

    ``signatures`` carries simhash ints for the default method and
    :class:`datasketch.MinHash` instances for the MinHash method —
    field name renamed from ``fingerprints`` in Phase 12 so the
    method-agnostic role is obvious to readers.
    """

    info: Dict[str, Any]
    signatures: List[Any]
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
    dedup_method: str = "simhash",
    minhash_jaccard: float = DEFAULT_MINHASH_JACCARD,
    minhash_num_perm: int = DEFAULT_MINHASH_NUM_PERM,
    enable_quality_filter: bool = False,
    enable_pii_ml: bool = False,
    pii_ml_language: str = "en",
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
        info, signatures, pii_split, parse_errors, decode_errors = _audit_split(
            split_name,
            path,
            near_dup_threshold=near_dup_threshold,
            dedup_method=dedup_method,
            minhash_jaccard=minhash_jaccard,
            minhash_num_perm=minhash_num_perm,
            enable_quality_filter=enable_quality_filter,
            enable_pii_ml=enable_pii_ml,
            pii_ml_language=pii_ml_language,
        )
    except OSError as exc:
        logger.warning("Could not read split '%s' (%s): %s — skipping.", split_name, path, exc)
        return _SplitOutcome(
            info={"error": f"read_failed: {exc}", "path": str(path)},
            signatures=[],
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
        signatures=signatures,
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

    A snapshot of :data:`PII_SEVERITY` (regex categories) and
    :data:`PII_ML_SEVERITY` (Phase 12.5 ML-NER categories) is taken at
    call time so a test or downstream caller mutating either dict
    cannot corrupt the audit output mid-run; per-call audits see a
    stable merged table for the duration of their work. The two
    tables share the same tier vocabulary (``critical/high/medium/low``)
    on purpose so the verdict surface stays unified.
    """
    severity_table = {**PII_SEVERITY, **PII_ML_SEVERITY}
    if not pii_summary:
        return {
            "total": 0,
            "by_tier": dict.fromkeys(PII_SEVERITY_ORDER, 0),
            "by_type": {},
            "worst_tier": None,
        }

    by_tier: Dict[str, int] = dict.fromkeys(PII_SEVERITY_ORDER, 0)
    by_type: Dict[str, Dict[str, Any]] = {}
    total = 0
    worst_tier_idx: Optional[int] = None

    for kind, count in pii_summary.items():
        if count <= 0:
            continue
        tier = severity_table.get(kind, "unknown")
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


def _secrets_summary_notes(secrets_summary: Dict[str, int]) -> List[str]:
    """Operator-actionable note when credentials/keys land in the corpus.

    Compliance-critical: a leaked AWS / GitHub / OpenAI key in the
    training data gets memorised at SFT time. The message is loud
    (``CRITICAL``) on purpose — operators must see this above any
    PII / quality noise.
    """
    if not secrets_summary:
        return []
    total = sum(secrets_summary.values())
    breakdown = ", ".join(f"{k}={v}" for k, v in sorted(secrets_summary.items()))
    return [
        f"CRITICAL: {total} credential/secret span(s) detected ({breakdown}). "
        "Scrub before training with `forgelm ingest --secrets-mask` (Phase 12) "
        "or the regex helpers in `forgelm.data_audit.mask_secrets`."
    ]


def _quality_summary_notes(quality_summary: Dict[str, Any]) -> List[str]:
    """Operator-actionable note for the heuristic quality filter."""
    if not quality_summary or not quality_summary.get("samples_flagged"):
        return []
    flagged = quality_summary["samples_flagged"]
    by_check = quality_summary.get("by_check", {})
    breakdown = ", ".join(f"{k}={v}" for k, v in sorted(by_check.items()))
    return [
        f"Quality filter flagged {flagged} sample(s) ({breakdown}). "
        "Heuristics are intentionally conservative; review the offending "
        "rows before deciding to drop them. Pass `--quality-filter` again "
        "after fixes to re-measure."
    ]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _fold_outcome_into_summary(
    outcome: "_SplitOutcome",
    *,
    pii_summary: Dict[str, int],
    secrets_summary: Dict[str, int],
    quality_aggregate: Dict[str, int],
    enable_quality_filter: bool,
) -> Tuple[int, int]:
    """Merge a single split's findings into the cross-split aggregates.

    Returns ``(quality_samples_flagged, quality_samples_evaluated)`` so the
    caller can keep both numerator and denominator running totals without
    re-reading the outcome.
    """
    for kind, count in outcome.pii_split.items():
        pii_summary[kind] = pii_summary.get(kind, 0) + count
    for kind, count in outcome.info.get("secrets_counts", {}).items():
        secrets_summary[kind] = secrets_summary.get(kind, 0) + count
    if not enable_quality_filter:
        return 0, 0
    for kind, count in outcome.info.get("quality_flags_counts", {}).items():
        quality_aggregate[kind] = quality_aggregate.get(kind, 0) + count
    return (
        outcome.info.get("quality_samples_flagged", 0),
        outcome.info.get("quality_samples_evaluated", 0),
    )


def _build_quality_summary(
    *,
    enable_quality_filter: bool,
    samples_flagged_total: int,
    quality_aggregate: Dict[str, int],
    samples_evaluated_total: int,
) -> Dict[str, Any]:
    """Render the ``quality_summary`` block (empty dict when filter is off).

    The denominator is the number of rows that were actually run through
    :func:`_row_quality_flags` — null/empty/non-dict rows are excluded
    because the filter can't evaluate them, and including them would
    silently depress the overall score (a corpus that's 50 % null but
    100 % clean on the rest would otherwise read 0.5 instead of 1.0).
    """
    if not enable_quality_filter:
        return {}
    if samples_evaluated_total:
        overall_score = round(1.0 - (samples_flagged_total / samples_evaluated_total), 4)
    else:
        overall_score = 1.0
    return {
        "samples_flagged": samples_flagged_total,
        "samples_evaluated": samples_evaluated_total,
        "by_check": quality_aggregate,
        "overall_quality_score": overall_score,
    }


# Phase 12.5: Google Croissant 1.0 dataset-card emission. Croissant is a
# JSON-LD vocabulary built on top of schema.org; mlcommons.org/croissant
# describes the canonical context. We emit a minimum-viable subset that's
# valid against the spec — tools that consume Croissant (HuggingFace's
# dataset-cards, Croissant validator, MLCommons reference loaders) can
# parse the block without modification, while the rest of the audit JSON
# stays untouched. The card lives under the new ``croissant`` key on the
# ``AuditReport`` dataclass; callers that don't want it never see it.

# JSON-LD reserved keywords used as dict keys in the Croissant card body.
# The W3C JSON-LD 1.1 spec fixes these tokens — they're vocabulary
# constants, not arbitrary strings, but Sonar's S1192 (string-literals-
# duplicated) flags the repeated literal use across the metadata
# builder. Hoisting them here keeps the rule satisfied without
# obscuring that we're emitting standardized JSON-LD framing.
_JSONLD_TYPE_KEY: str = "@type"
_JSONLD_ID_KEY: str = "@id"

_CROISSANT_CONTEXT: Dict[str, Any] = {
    "@language": "en",
    "@vocab": "https://schema.org/",
    "sc": "https://schema.org/",
    # ``cr:`` is the canonical Croissant 1.0 JSON-LD namespace IRI as
    # defined by the mlcommons.org/croissant spec — an RDF identifier,
    # not a network endpoint. Strict consumers (mlcroissant validator,
    # MLCommons reference loaders) compare this string lexically; using
    # ``https://`` here would diverge from the spec-canonical form and
    # break exact-match consumers. The S5332 hotspot is a false positive
    # for this dual-purpose URI.
    "cr": "http://mlcommons.org/croissant/",  # NOSONAR — JSON-LD namespace IRI, not a fetch URL
    "data": {"@id": "cr:data", "@type": "@json"},
    "dataType": {"@id": "cr:dataType", "@type": "@vocab"},
    "extract": "cr:extract",
    "field": "cr:field",
    "fileProperty": "cr:fileProperty",
    "format": "cr:format",
    "includes": "cr:includes",
    "isLiveDataset": "cr:isLiveDataset",
    "jsonPath": "cr:jsonPath",
    "key": "cr:key",
    "parentField": "cr:parentField",
    "path": "cr:path",
    "recordSet": "cr:recordSet",
    "references": "cr:references",
    "regex": "cr:regex",
    "repeated": "cr:repeated",
    "replace": "cr:replace",
    "separator": "cr:separator",
    "source": "cr:source",
    "subField": "cr:subField",
    "transform": "cr:transform",
}


def _build_croissant_metadata(
    *,
    source_path: str,
    source_input: str,
    generated_at: str,
    total_samples: int,
    splits_info: Dict[str, Dict[str, Any]],
    splits_paths: Dict[str, Path],
) -> Dict[str, Any]:
    """Render a minimum-viable Croissant 1.0 dataset card for the audited corpus.

    The card exposes:
    * dataset-level identity (name, description, version, datePublished),
    * one ``cr:FileObject`` per JSONL split (so a Croissant consumer can
      locate the underlying files),
    * one ``cr:RecordSet`` per split with the columns the audit detected
      under ``splits.<name>.columns`` mapped to ``cr:Field`` entries.

    The mapping intentionally stays additive — Croissant supports many
    optional fields (citeAs, license, keywords, sameAs, etc.) that the
    audit does not have first-class evidence for. Operators that want to
    publish the card to HuggingFace / MLCommons can hand-edit those
    fields without re-running the audit.
    """
    # Derive a human-readable name from the source path. ``Path.stem`` for
    # a JSONL ("policies.jsonl" → "policies"); for a directory we use the
    # directory name. Fall back to ``source_input`` so HF Hub IDs survive
    # in the card even though the audit is filesystem-only today.
    src = Path(source_path)
    if src.is_file():
        name = src.stem
    elif src.is_dir():
        name = src.name
    else:
        name = source_input or "dataset"

    distribution: List[Dict[str, Any]] = []
    record_sets: List[Dict[str, Any]] = []
    for split_name, info in splits_info.items():
        sample_count = int(info.get("sample_count", 0))
        # Derive ``file_id`` from the real source filename (basename
        # only, never the absolute path) so single-file audits like
        # ``policies.jsonl`` don't show up as ``train.jsonl`` in the
        # generated card and alias layouts (``dev.jsonl`` → split
        # ``validation``) keep their on-disk filename. Falls back to
        # the canonical ``{split}.jsonl`` shape when no path is
        # registered — defensive for callers that bypass
        # ``_resolve_input``.
        split_path = splits_paths.get(split_name)
        file_id = split_path.name if split_path else f"{split_name}.jsonl"
        # ``contentUrl`` deliberately uses the *file_id* (relative
        # filename), not the absolute filesystem path: cards published
        # to HuggingFace / MLCommons must not leak the auditor's local
        # ``/Users/...`` / ``/home/builder/...`` layout. Operators that
        # want a real ``contentUrl`` (HF Hub URL, S3 path, etc.) can
        # hand-edit the field at publish time the same way they do
        # ``license`` / ``citeAs``.
        distribution.append(
            {
                _JSONLD_TYPE_KEY: "cr:FileObject",
                _JSONLD_ID_KEY: file_id,
                "name": file_id,
                "contentUrl": file_id,
                "encodingFormat": "application/jsonlines",
                "description": f"Split {split_name!r}: {sample_count} sample(s).",
            }
        )

        # Map the audit's detected columns to ``cr:Field`` entries.
        # ``columns`` is a list of strings (the keys present in the JSONL
        # rows). When the column is one of the canonical text-payload
        # columns we type it as ``sc:Text``; everything else is ``sc:Text``
        # too (the audit doesn't track per-column dtypes — that's a
        # consumer-side concern).
        columns = info.get("columns") or []
        fields = [
            {
                _JSONLD_TYPE_KEY: "cr:Field",
                _JSONLD_ID_KEY: f"{split_name}/{column}",
                "name": column,
                "dataType": "sc:Text",
                "source": {
                    "fileObject": {_JSONLD_ID_KEY: file_id},
                    "extract": {"jsonPath": f"$.{column}"},
                },
            }
            for column in columns
        ]
        record_sets.append(
            {
                _JSONLD_TYPE_KEY: "cr:RecordSet",
                _JSONLD_ID_KEY: split_name,
                "name": split_name,
                "field": fields,
                "description": f"Records from split {split_name!r}.",
            }
        )

    # ``url`` carries the basename of ``source_input`` so we never
    # publish an auditor's absolute filesystem path
    # (``/Users/...`` / ``/home/builder/...``) into a card that may be
    # shipped to HuggingFace / MLCommons. ``Path.name`` gives the
    # relative form for both files (``policies.jsonl``) and directories
    # (``data/`` → ``data``); when ``source_input`` is empty we fall
    # back to the dataset name. Operators that want a real public URL
    # (HF Hub, S3) hand-edit at publish time, the same way they do
    # ``license`` / ``citeAs``.
    # ``version`` (``sc:version``) describes the *dataset* version,
    # not the Croissant vocabulary version (vocab conformance is
    # declared via ``conformsTo``). The audit doesn't have first-class
    # evidence for dataset version, so the field is omitted; operators
    # that publish the card hand-edit ``version`` like they do
    # ``license`` / ``citeAs``.
    url_safe = Path(source_input).name if source_input else name
    return {
        "@context": dict(_CROISSANT_CONTEXT),
        _JSONLD_TYPE_KEY: "sc:Dataset",
        # ``conformsTo`` declares the Croissant vocabulary version the
        # card adheres to. Like ``cr:`` above, this is a JSON-LD URI
        # identifier (RDF reference), not a network endpoint — strict
        # consumers exact-match the canonical spec form. Same S5332
        # false-positive rationale as ``cr:`` in ``_CROISSANT_CONTEXT``.
        "conformsTo": "http://mlcommons.org/croissant/1.0",  # NOSONAR — JSON-LD identifier
        "name": name,
        "description": (
            "ForgeLM audit-generated dataset card. "
            f"{total_samples} sample(s) across {len(splits_info)} split(s). "
            "Inline counts/quality/PII summaries live in the parent "
            "data_audit_report.json under the canonical audit keys."
        ),
        "url": url_safe,
        "datePublished": generated_at,
        "distribution": distribution,
        "recordSet": record_sets,
    }


def _build_near_duplicate_summary(
    *,
    dedup_method: str,
    near_dup_pairs: Dict[str, int],
    near_dup_threshold: int,
    minhash_jaccard: float,
    minhash_num_perm: int,
) -> Dict[str, Any]:
    """Pack the ``near_duplicate_summary`` block with method-specific params."""
    summary: Dict[str, Any] = {
        "method": dedup_method,
        "pairs_per_split": near_dup_pairs,
    }
    if dedup_method == "minhash":
        summary["jaccard_threshold"] = minhash_jaccard
        summary["num_perm"] = minhash_num_perm
    else:
        summary["hamming_threshold"] = near_dup_threshold
    return summary


def audit_dataset(
    source: str,
    *,
    output_dir: Optional[str] = None,
    near_dup_threshold: int = DEFAULT_NEAR_DUP_HAMMING,
    dedup_method: str = "simhash",
    minhash_jaccard: float = DEFAULT_MINHASH_JACCARD,
    minhash_num_perm: int = DEFAULT_MINHASH_NUM_PERM,
    enable_quality_filter: bool = False,
    enable_pii_ml: bool = False,
    pii_ml_language: str = "en",
    emit_croissant: bool = False,
) -> AuditReport:
    """Run the audit pipeline over a JSONL file or split-keyed directory.

    Args:
        source: Path to a ``.jsonl`` file (single split) or a directory
            containing ``train.jsonl`` / ``validation.jsonl`` / ``test.jsonl``.
        output_dir: When set, writes ``data_audit_report.json`` under this
            directory (created if missing). Returned :class:`AuditReport`
            is identical either way.
        near_dup_threshold: Hamming distance cutoff for the simhash-based
            near-duplicate detector. Default 3 (≈95% similarity). Ignored
            when ``dedup_method="minhash"``.
        dedup_method: Phase 12 — ``"simhash"`` (default; exact recall via
            LSH banding) or ``"minhash"`` (datasketch MinHash LSH; the
            industry standard above ~50K rows). MinHash requires the
            optional ``[ingestion-scale]`` extra.
        minhash_jaccard: Jaccard-similarity threshold for the MinHash
            method. Default ``0.85`` ≈ simhash's ``threshold=3`` in
            similarity terms.
        minhash_num_perm: Number of permutations for ``datasketch.MinHash``.
            Default ``128`` matches datasketch's own default.
        enable_pii_ml: Phase 12.5 opt-in — layer Presidio's ML-NER PII
            detector (``person`` / ``organization`` / ``location``) on
            top of the regex detector. Requires the optional
            ``[ingestion-pii-ml]`` extra AND a spaCy NER model
            (``python -m spacy download en_core_web_lg``); raises
            ``ImportError`` with the install hint when either is
            missing so the failure surfaces before any rows are scanned.
        pii_ml_language: Phase 12.5 — language code passed to Presidio's
            NLP engine. Default ``"en"``. Set to ``"tr"`` (or whichever
            spaCy model the operator has loaded) for non-English
            corpora; Presidio raises a typed exception when no engine
            is registered for the requested language.
        emit_croissant: Phase 12.5 opt-in flag — when ``True``, populate
            the report's ``croissant`` field with a Google Croissant 1.0
            dataset card (``@type: sc:Dataset``) so the same JSON file
            doubles as both the EU AI Act Article 10 governance artifact
            and a Croissant-consumer dataset card. Off by default — older
            consumers see byte-identical output until they opt in.
        enable_quality_filter: Phase 12 opt-in flag — when ``True``, run
            the heuristic quality checks (Gopher / C4 / RefinedWeb-style)
            and surface findings under ``quality_summary``.

    Returns:
        :class:`AuditReport`. JSON-serialize via ``asdict(report)``.
    """
    if dedup_method not in DEDUP_METHODS:
        raise ValueError(f"dedup_method must be one of {DEDUP_METHODS}; got {dedup_method!r}.")
    if dedup_method == "minhash":
        if not isinstance(minhash_jaccard, (int, float)) or isinstance(minhash_jaccard, bool):
            raise ValueError(f"minhash_jaccard must be a float in [0.0, 1.0]; got {minhash_jaccard!r}.")
        if not 0.0 <= float(minhash_jaccard) <= 1.0:
            raise ValueError(f"minhash_jaccard must be in [0.0, 1.0]; got {minhash_jaccard!r}.")
        if not isinstance(minhash_num_perm, int) or isinstance(minhash_num_perm, bool) or minhash_num_perm <= 0:
            raise ValueError(f"minhash_num_perm must be a positive integer; got {minhash_num_perm!r}.")
        _require_datasketch()
    if enable_pii_ml:
        # Phase 12.5: pre-flight the optional extra AND the requested
        # language so the caller learns the dep / model / language is
        # missing BEFORE we open any files / scan any rows, mirroring
        # the ``_require_datasketch`` shape above. Without the language
        # check, ``--pii-ml-language tr`` against a default Presidio
        # install would silently return ``{}`` per row (analyzer raises
        # ``ValueError`` which ``detect_pii_ml`` deliberately swallows
        # for per-row resilience on pathological strings).
        _require_presidio(language=pii_ml_language)

    splits_paths, resolution_notes = _resolve_input(source)

    splits_info: Dict[str, Dict[str, Any]] = {}
    signatures_by_split: Dict[str, List[Any]] = {}
    pii_summary: Dict[str, int] = {}
    secrets_summary: Dict[str, int] = {}
    quality_aggregate: Dict[str, int] = {}
    quality_samples_flagged_total = 0
    quality_samples_evaluated_total = 0
    total_samples = 0
    near_dup_pairs: Dict[str, int] = {}
    notes: List[str] = list(resolution_notes)

    parse_errors_total = 0
    decode_errors_total = 0

    for split_name, path in splits_paths.items():
        outcome = _process_split(
            split_name,
            path,
            near_dup_threshold=near_dup_threshold,
            dedup_method=dedup_method,
            minhash_jaccard=minhash_jaccard,
            minhash_num_perm=minhash_num_perm,
            enable_quality_filter=enable_quality_filter,
            enable_pii_ml=enable_pii_ml,
            pii_ml_language=pii_ml_language,
        )
        splits_info[split_name] = outcome.info
        signatures_by_split[split_name] = outcome.signatures
        total_samples += outcome.row_count
        near_dup_pairs[split_name] = outcome.info.get("near_duplicate_pairs", 0)
        notes.extend(outcome.split_notes)
        parse_errors_total += outcome.parse_errors
        decode_errors_total += outcome.decode_errors
        flagged, evaluated = _fold_outcome_into_summary(
            outcome,
            pii_summary=pii_summary,
            secrets_summary=secrets_summary,
            quality_aggregate=quality_aggregate,
            enable_quality_filter=enable_quality_filter,
        )
        quality_samples_flagged_total += flagged
        quality_samples_evaluated_total += evaluated

    cross = _cross_split_overlap(
        signatures_by_split,
        dedup_method=dedup_method,
        threshold=near_dup_threshold,
        minhash_jaccard=minhash_jaccard,
        minhash_num_perm=minhash_num_perm,
    )
    pii_severity = _build_pii_severity(pii_summary)
    quality_summary = _build_quality_summary(
        enable_quality_filter=enable_quality_filter,
        samples_flagged_total=quality_samples_flagged_total,
        quality_aggregate=quality_aggregate,
        samples_evaluated_total=quality_samples_evaluated_total,
    )

    notes.extend(_pii_summary_notes(pii_summary, pii_severity))
    notes.extend(_secrets_summary_notes(secrets_summary))
    notes.extend(_quality_summary_notes(quality_summary))
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

    near_duplicate_summary = _build_near_duplicate_summary(
        dedup_method=dedup_method,
        near_dup_pairs=near_dup_pairs,
        near_dup_threshold=near_dup_threshold,
        minhash_jaccard=minhash_jaccard,
        minhash_num_perm=minhash_num_perm,
    )

    generated_at = datetime.now(timezone.utc).isoformat()
    source_path_abs = os.fspath(Path(source).expanduser().resolve())
    croissant: Dict[str, Any] = {}
    if emit_croissant:
        croissant = _build_croissant_metadata(
            source_path=source_path_abs,
            source_input=source,
            generated_at=generated_at,
            total_samples=total_samples,
            splits_info=splits_info,
            splits_paths=splits_paths,
        )

    report = AuditReport(
        generated_at=generated_at,
        source_path=source_path_abs,
        source_input=source,
        total_samples=total_samples,
        splits=splits_info,
        cross_split_overlap=cross,
        pii_summary=pii_summary,
        pii_severity=pii_severity,
        near_duplicate_summary=near_duplicate_summary,
        secrets_summary=secrets_summary,
        quality_summary=quality_summary,
        croissant=croissant,
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
        "secrets_counts",
        "quality_flags_counts",
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
    """Operator-friendly rendering of one split's metrics. One concern per call.

    JSONL hygiene counters (``parse_errors``, ``decode_errors``,
    ``non_object_rows``) are surfaced **before** the body metrics so a
    malformed split is flagged at the top of the block — :func:`_split_has_findings`
    promotes splits that carry any of these, and the operator should see the
    reason ahead of length/PII/etc. lines that follow.
    """
    block: List[str] = [f"  └─ {split_name}: n={info.get('sample_count', 0)}"]
    if "error" in info:
        block.append(f"     ERROR        : {info['error']}")
        return block
    if info.get("parse_errors"):
        block.append(f"     parse errors    : {info['parse_errors']} (malformed JSONL line(s) skipped)")
    if info.get("decode_errors"):
        block.append(f"     decode errors   : {info['decode_errors']} (non-UTF-8 byte(s) replaced with U+FFFD)")
    if info.get("non_object_rows"):
        block.append(f"     non-object rows : {info['non_object_rows']} (valid JSON but not a dict)")
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
    if info.get("secrets_counts"):
        secrets = ", ".join(f"{k}={v}" for k, v in sorted(info["secrets_counts"].items()))
        block.append(f"     secrets         : {secrets}")
    if info.get("quality_flags_counts"):
        quality = ", ".join(f"{k}={v}" for k, v in sorted(info["quality_flags_counts"].items()))
        block.append(f"     quality flags   : {quality} (samples_flagged={info.get('quality_samples_flagged', 0)})")
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
    if report.secrets_summary:
        total = sum(report.secrets_summary.values())
        breakdown = ", ".join(f"{k}={v}" for k, v in sorted(report.secrets_summary.items()))
        lines.append(f"  Secrets        : CRITICAL — {total} flagged ({breakdown})")
    if report.quality_summary and report.quality_summary.get("samples_flagged"):
        score = report.quality_summary.get("overall_quality_score", 0.0)
        flagged = report.quality_summary["samples_flagged"]
        lines.append(f"  Quality        : {flagged} sample(s) flagged (overall score = {score:.4f})")

    if report.cross_split_overlap.get("pairs"):
        method = report.cross_split_overlap.get("method", "simhash")
        lines.append(f"  Cross-split leakage ({method}):")
        for pair_name, payload in report.cross_split_overlap["pairs"].items():
            lines.append(f"    {pair_name}: {payload}")
    return "\n".join(lines)
