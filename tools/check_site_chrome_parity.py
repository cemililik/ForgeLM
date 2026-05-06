"""Advisory: report chrome-translation key drift across the six-locale registry.

`site/js/translations.js` carries the marketing-site chrome strings in six
languages (EN, TR, DE, FR, ES, ZH). Per `docs/standards/localization.md`,
EN and TR are **active tiers** (every chrome key must be present in both),
while DE, FR, ES, ZH are **deferred tiers** that may lag between releases
(missing keys fall back to EN at runtime via the i18n chain).

This guard parses the file and reports:

  * EN ↔ TR drift (any drift here is a bug — the active-tier parity rule).
  * DE/FR/ES/ZH gap vs EN (advisory only — expected to be non-zero until
    the v0.6.x native-review cycle clears the deferred-tier debt).

Default mode is **advisory** (exit 0 even with deferred-tier drift, so a
local run never blocks a release cut). `--strict` fails on any drift —
including the deferred tiers — and is intentionally NOT wired into CI at
v0.5.5 per the deferred-tier policy. Operators may run `--strict` locally
to audit the gap when planning the v0.6.x translation pass.

EN ↔ TR drift, however, is *always* a failure regardless of mode (matches
the active-tier rule in `docs/standards/localization.md`).

Usage::

    python3 tools/check_site_chrome_parity.py             # advisory report
    python3 tools/check_site_chrome_parity.py --strict    # fail on any drift

See `docs/roadmap/risks-and-decisions.md` for the v0.6.x activation plan
that promotes this guard from local-only to CI-enforced once the
deferred-tier translations have had a native-review pass.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Match `Object.assign(T.<lang>, {` block openers — used for every page-level
# extension below the initial direct `T.<lang> = {...}` definitions.
_BLOCK_RE = re.compile(r"Object\.assign\(\s*T\.(\w+)\s*,\s*\{")

# Match the initial `T.<lang> = {` direct assignment (the first common-block
# definition for each language at the top of the file).
_DIRECT_RE = re.compile(r"^\s*T\.(\w+)\s*=\s*\{")

# Match a top-level key inside a block: a `"key": ...` line at the outermost
# brace level. We rely on indentation only as a tiebreaker against nested
# objects, but in practice translations.js holds flat string maps so the
# brace-depth tracker is sufficient.
_KEY_RE = re.compile(r'^\s*"([^"]+)"\s*:')

_TIERS_ACTIVE: tuple[str, ...] = ("en", "tr")
_TIERS_DEFERRED: tuple[str, ...] = ("de", "fr", "es", "zh")
_ALL_TIERS: tuple[str, ...] = _TIERS_ACTIVE + _TIERS_DEFERRED


class _BlockState:
    """Mutable cursor for ``_parse_blocks`` — folded into a class so the
    main parse loop reads as a flat sequence of small steps rather than a
    nested branching ladder."""

    __slots__ = ("in_block", "current_lang", "current_keys", "brace_depth")

    def __init__(self) -> None:
        self.in_block = False
        self.current_lang: str | None = None
        self.current_keys: set[str] = set()
        self.brace_depth = 0

    def open(self, lang: str) -> None:
        self.in_block = True
        self.current_lang = lang
        self.current_keys = set()
        self.brace_depth = 1

    def close(self) -> tuple[str | None, set[str]]:
        finished = (self.current_lang, self.current_keys)
        self.in_block = False
        self.current_lang = None
        self.current_keys = set()
        return finished


def _try_open_block(line: str, state: _BlockState) -> None:
    match = _BLOCK_RE.search(line) or _DIRECT_RE.search(line)
    if match:
        state.open(match.group(1))


def _process_block_line(line: str, state: _BlockState, aggregated: dict[str, set[str]]) -> None:
    if state.brace_depth == 1:
        key_match = _KEY_RE.match(line)
        if key_match:
            state.current_keys.add(key_match.group(1))
    state.brace_depth += line.count("{") - line.count("}")
    if state.brace_depth <= 0:
        lang, keys = state.close()
        if lang in aggregated:
            aggregated[lang].update(keys)


def _parse_blocks(source: str) -> dict[str, set[str]]:
    """Return ``{lang_code: set_of_keys}`` aggregated across every block.

    Walks the source line by line, tracks brace depth, and collects keys at
    depth-1 (i.e. direct properties of the block object, not nested map
    values). Multiple blocks per language are unioned.
    """
    aggregated: dict[str, set[str]] = {lang: set() for lang in _ALL_TIERS}
    state = _BlockState()
    for line in source.split("\n"):
        if not state.in_block:
            _try_open_block(line, state)
            continue
        _process_block_line(line, state, aggregated)
    return aggregated


def _format_sample(keys: set[str], limit: int = 5) -> str:
    sample = sorted(keys)[:limit]
    suffix = f" (+{len(keys) - limit} more)" if len(keys) > limit else ""
    return ", ".join(sample) + suffix


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Advisory check for site chrome translation parity.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Fail (exit 1) on any deferred-tier drift. NOT wired into CI — "
            "use locally to audit the v0.6.x translation backlog."
        ),
    )
    parser.add_argument(
        "--js-path",
        type=Path,
        default=None,
        help="Override path to translations.js (defaults to site/js/translations.js).",
    )
    return parser


def _check_active_tier(en_keys: set[str], tr_keys: set[str]) -> bool:
    """Return ``True`` iff EN ↔ TR are in lockstep (no drift)."""
    en_only = en_keys - tr_keys
    tr_only = tr_keys - en_keys
    if not (en_only or tr_only):
        print("  EN <-> TR: in lockstep (active tier OK)")
        return True
    print()
    print("FAIL: EN <-> TR drift (active-tier parity rule violated)")
    if en_only:
        print(f"  in EN, missing in TR ({len(en_only)}): {_format_sample(en_only)}")
    if tr_only:
        print(f"  in TR, missing in EN ({len(tr_only)}): {_format_sample(tr_only)}")
    return False


def _report_deferred_tiers(blocks: dict[str, set[str]], en_keys: set[str]) -> bool:
    """Print per-deferred-tier drift; return ``True`` iff any tier drifted."""
    print()
    print("deferred-tier (DE/FR/ES/ZH) drift vs EN:")
    has_drift = False
    for lang in _TIERS_DEFERRED:
        lang_keys = blocks.get(lang, set())
        missing = en_keys - lang_keys
        extra = lang_keys - en_keys
        if missing:
            has_drift = True
            print(f"  INFO: {lang.upper()} missing {len(missing)} keys vs EN -> {_format_sample(missing)}")
        else:
            print(f"  OK:   {lang.upper()} carries every EN key")
        if extra:
            print(f"  WARN: {lang.upper()} has {len(extra)} keys not in EN -> {_format_sample(extra)}")
    return has_drift


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    project_root = Path(__file__).resolve().parent.parent
    js_path = args.js_path or (project_root / "site" / "js" / "translations.js")
    if not js_path.is_file():
        print(f"FAIL: translations.js not found at {js_path}", file=sys.stderr)
        return 1

    source = js_path.read_text(encoding="utf-8")
    blocks = _parse_blocks(source)
    en_keys = blocks.get("en", set())
    tr_keys = blocks.get("tr", set())

    print(f"site chrome parity report ({js_path.relative_to(project_root)})")
    print(f"  total EN keys: {len(en_keys)}")
    print(f"  total TR keys: {len(tr_keys)}")

    if not _check_active_tier(en_keys, tr_keys):
        return 1

    if _report_deferred_tiers(blocks, en_keys):
        print()
        print(
            "Note: deferred-tier drift is expected per "
            "docs/standards/localization.md. The v0.6.x native-review cycle "
            "clears this backlog; do NOT machine-translate to close the gap."
        )
        if args.strict:
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
