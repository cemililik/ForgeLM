"""Phase 12: MinHash LSH near-duplicate detection (optional ``datasketch``).

Mirrors the simhash module's API surface so the per-split callsite can
swap one for the other on a method flag. ``compute_minhash`` returns
``None`` for empty input — analogous to simhash's ``0`` sentinel —
which downstream pair-walks treat as "skip".
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from . import _optional
from ._simhash import _tokenize
from ._types import DEFAULT_MINHASH_JACCARD, DEFAULT_MINHASH_NUM_PERM


def _require_datasketch() -> None:
    """Raise a clear ImportError when the optional MinHash backend is missing."""
    if not _optional._HAS_DATASKETCH:
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
    m = _optional._MinHash(num_perm=num_perm)
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
    """Build an LSH index over non-empty MinHashes; return ``(lsh, key->idx)``."""
    lsh = _optional._MinHashLSH(threshold=jaccard_threshold, num_perm=num_perm)
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
    """Pair-find rows whose MinHash Jaccard similarity >= ``jaccard_threshold``.

    Returns ``[(i, j, jaccard), ...]`` with ``i < j``. Mirrors
    :func:`find_near_duplicates`'s shape so the per-split callsite can
    swap one for the other on a method flag.

    Implementation: a single :class:`datasketch.MinHashLSH` index over all
    non-``None`` MinHashes — average-case ``O(n x k)`` where ``k`` is the
    band-bucket fan-out; cluster-collision worst case is still ``O(n^2)``
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
    """Rows in ``source`` whose nearest target MinHash has Jaccard >= threshold.

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
    first candidate whose actual Jaccard >= threshold is enough to flag a leak,
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
    separate calls, paying the construction cost 2x per direction pair.
    This function builds each index once and reuses it for both queries,
    halving the dominant ``O(n_b x bands)`` / ``O(n_a x bands)`` cost.
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


__all__ = [
    "_require_datasketch",
    "compute_minhash",
    "_build_minhash_lsh",
    "_emit_minhash_pair",
    "find_near_duplicates_minhash",
    "_count_leaked_rows_minhash",
    "_count_leaks_against_index",
    "_count_leaked_rows_minhash_bidirectional",
]
