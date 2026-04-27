"""Microbenchmark: xxh3_64 vs blake2b on the per-token simhash hot path.

Phase 11.5 added an optional xxhash backend behind ``_token_digest`` and a
module-scope ``lru_cache``. The well-known "4-10× faster" figure xxhash
advertises refers to C-level pure-hash benchmarks; the Python wrapping
(``encode`` → call → ``intdigest``) narrows the gap considerably.

This script measures both the **raw digest cost** (no cache) AND the
**end-to-end** ``compute_simhash`` cost so the perf claims in the docs and
CHANGELOG stay grounded in numbers.

Run manually — it is **not** part of ``pytest`` because wall-clock timing is
noisy on shared CI:

    python tests/bench_simhash.py

Results are written to stdout; copy the table back into
``docs/roadmap/phase-11-5-backlog.md`` if it has shifted materially after
a backend / dependency / Python version change.

Security note: ``random.choices`` / ``random.randint`` are used purely to
synthesise corpus-shaped test inputs — there is no security-sensitive
context in this script and no value derived from these calls is ever
returned, persisted, or compared cryptographically. The ``# NOSONAR``
suppressions on each call site annotate that explicitly so the
SonarCloud ``python:S2245`` rule does not flag them as findings.
"""

from __future__ import annotations

import hashlib
import random
import statistics
import string
import time

import xxhash  # type: ignore  # optional; only required to run this script

from forgelm import data_audit as audit_mod


def _gen_short(n: int) -> list[str]:
    return [
        "".join(
            random.choices(string.ascii_lowercase, k=random.randint(2, 6))  # NOSONAR(python:S2245)
        )
        for _ in range(n)
    ]


def _gen_zipfian_english(n: int) -> list[str]:
    base = [
        "the",
        "of",
        "and",
        "a",
        "to",
        "in",
        "is",
        "for",
        "with",
        "on",
        "by",
        "this",
        "that",
        "from",
        "as",
        "an",
        "be",
        "or",
        "not",
        "but",
    ]
    return random.choices(base, k=n)  # NOSONAR(python:S2245)


def _gen_long(n: int) -> list[str]:
    return [
        "".join(
            random.choices(string.ascii_lowercase, k=random.randint(40, 80))  # NOSONAR(python:S2245)
        )
        for _ in range(n)
    ]


def _bench_raw(tokens: list[str], repeats: int = 21) -> dict:
    encoded = [t.encode("utf-8") for t in tokens]

    def _xxh3() -> None:
        # Bench harness only: assigning to ``_`` documents that the
        # return value is intentionally discarded. The hashlib path
        # below now does the same so the two loops stay symmetrical.
        for b in encoded:
            _ = xxhash.xxh3_64(b).intdigest()

    def _blake() -> None:
        for b in encoded:
            _ = int.from_bytes(hashlib.blake2b(b, digest_size=8).digest(), "big")

    _xxh3()
    _blake()

    xxh3_times = []
    blake_times = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        _xxh3()
        xxh3_times.append(time.perf_counter() - t0)
        t0 = time.perf_counter()
        _blake()
        blake_times.append(time.perf_counter() - t0)

    return {
        "xxh3_median_s": statistics.median(xxh3_times),
        "blake_median_s": statistics.median(blake_times),
        "speedup": statistics.median(blake_times) / statistics.median(xxh3_times),
    }


def _bench_compute_simhash(repeats: int = 5) -> dict:
    """End-to-end through compute_simhash. Measures impact AFTER lru_cache hits."""
    audit_mod._token_digest.cache_clear()

    base = ["the", "of", "and", "a", "to", "in", "is", "for", "with", "on"]
    texts = []
    for _ in range(1000):
        n = random.randint(50, 150)  # NOSONAR(python:S2245)
        texts.append(" ".join(random.choices(base, k=n)))  # NOSONAR(python:S2245)

    audit_mod._HAS_XXHASH = True
    for t in texts:
        audit_mod.compute_simhash(t)

    xxh3_times = []
    for _ in range(repeats):
        audit_mod._token_digest.cache_clear()
        t0 = time.perf_counter()
        for t in texts:
            audit_mod.compute_simhash(t)
        xxh3_times.append(time.perf_counter() - t0)

    audit_mod._HAS_XXHASH = False
    blake_times = []
    for _ in range(repeats):
        audit_mod._token_digest.cache_clear()
        t0 = time.perf_counter()
        for t in texts:
            audit_mod.compute_simhash(t)
        blake_times.append(time.perf_counter() - t0)

    audit_mod._HAS_XXHASH = bool(getattr(audit_mod, "_xxhash", None))
    audit_mod._token_digest.cache_clear()
    return {
        "xxh3_median_s": statistics.median(xxh3_times),
        "blake_median_s": statistics.median(blake_times),
        "speedup": statistics.median(blake_times) / statistics.median(xxh3_times),
    }


def main() -> None:
    random.seed(42)  # NOSONAR(python:S2245) — deterministic seed for reproducible bench
    print("Raw digest microbenchmark (50K hashes per round, median of 21)")
    print("-" * 70)
    for label, gen in [
        ("short keys (2-6 chars)", _gen_short),
        ("Zipfian English (~3 chars)", _gen_zipfian_english),
        ("long keys (40-80 chars)", _gen_long),
    ]:
        tokens = gen(50_000)
        result = _bench_raw(tokens)
        print(
            f"  {label:30s}: speedup = {result['speedup']:.2f}x "
            f"(xxh3={result['xxh3_median_s'] * 1000:.1f}ms, "
            f"blake={result['blake_median_s'] * 1000:.1f}ms)"
        )

    print()
    print("End-to-end compute_simhash (1K texts × 50-150 tokens, cache cleared)")
    print("-" * 70)
    e2e = _bench_compute_simhash()
    print(
        f"  speedup = {e2e['speedup']:.2f}x "
        f"(xxh3={e2e['xxh3_median_s'] * 1000:.1f}ms, blake={e2e['blake_median_s'] * 1000:.1f}ms)"
    )


if __name__ == "__main__":
    main()
