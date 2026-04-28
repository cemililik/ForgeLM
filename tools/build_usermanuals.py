#!/usr/bin/env python3
"""Compile docs/usermanuals/<lang>/**/*.md into site/js/usermanuals/<lang>.js.

Usage:
    python3 tools/build_usermanuals.py            # build all languages
    python3 tools/build_usermanuals.py --check    # exit 1 if generated files
                                                  # are stale (CI guard)

The generated JS files are committed to the repository so the static site
keeps its "no build step" guarantee for end users — only contributors who
edit user-manual content need to re-run this script.

Source layout
-------------
    docs/usermanuals/
        _meta.yaml                      — navigation tree, page titles
        en/<section>/<page>.md          — canonical content
        tr/<section>/<page>.md          — translation
        de/<section>/<page>.md          — translation
        fr/<section>/<page>.md          — translation
        es/<section>/<page>.md          — translation
        zh/<section>/<page>.md          — translation

Output layout
-------------
    site/js/usermanuals/
        _index.js     — shared structure (sections + page titles for nav)
        en.js         — { "<section>/<page>": { html, headings, fallback } }
        tr.js
        ...
        zh.js

Markdown extras supported
-------------------------
    - Front matter (YAML between leading ---) → merged into page metadata.
    - GitHub-flavoured tables, fenced code blocks.
    - Admonition fences:

          :::tip
          Try this first.
          :::

      becomes a styled callout in the rendered output.
    - Heading anchors are auto-generated from heading text.

Dependencies
------------
    pip install markdown pyyaml

Run this script whenever you change anything under docs/usermanuals/.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

try:
    import yaml
except ImportError:
    print("error: PyYAML is required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

try:
    import markdown
except ImportError:
    print("error: markdown is required. Install with: pip install markdown", file=sys.stderr)
    sys.exit(2)


REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = REPO_ROOT / "docs" / "usermanuals"
OUTPUT_DIR = REPO_ROOT / "site" / "js" / "usermanuals"
META_FILE = SOURCE_DIR / "_meta.yaml"


@dataclass
class Page:
    section_id: str
    page_id: str
    titles: dict  # {lang: title}


@dataclass
class Section:
    id: str
    icon: str
    titles: dict
    pages: list  # list[Page]


def slugify(text: str) -> str:
    """Generate a URL-safe slug for heading anchors."""
    text = unicodedata.normalize("NFKD", text)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    text = re.sub(r"[-\s]+", "-", text)
    return text or "section"


def load_meta() -> tuple[list, list[Section]]:
    """Read _meta.yaml and return (languages, sections)."""
    if not META_FILE.exists():
        raise SystemExit(f"error: {META_FILE} not found")

    with META_FILE.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    languages = data.get("languages") or ["en"]
    sections = []
    for sec in data.get("sections", []):
        pages = [Page(section_id=sec["id"], page_id=p["id"], titles=p["title"]) for p in sec.get("pages", [])]
        sections.append(Section(id=sec["id"], icon=sec.get("icon", "file"), titles=sec["title"], pages=pages))
    return languages, sections


# ---------------------------------------------------------------------- markdown

# Match :::kind ... ::: blocks (kind in note|tip|warn|danger|info).
_ADMONITION_RE = re.compile(
    r"^:::(note|tip|warn|danger|info)\s*\n(.*?)\n:::\s*$",
    re.MULTILINE | re.DOTALL,
)

# Match ```mermaid ... ``` fenced code blocks (preserved verbatim for
# client-side rendering by the mermaid.js library).
_MERMAID_RE = re.compile(r"^```mermaid\s*\n(.*?)\n```\s*$", re.MULTILINE | re.DOTALL)


def preprocess_admonitions(text: str) -> str:
    """Replace :::kind ... ::: fences with HTML callout divs."""

    def repl(m: re.Match) -> str:
        kind = m.group(1)
        body = m.group(2).strip()
        # Render body as markdown by leaving it raw for the main pass — the
        # markdown library will process the inner content because we use a
        # blank line above the body. Prepend a blank line just in case.
        return f'<div class="callout callout-{kind}" markdown="1">\n\n{body}\n\n</div>'

    return _ADMONITION_RE.sub(repl, text)


def preprocess_mermaid(text: str) -> str:
    """Replace ```mermaid ... ``` fences with raw <div class="mermaid"> blocks.

    The markdown processor would otherwise wrap the content in <pre><code> and
    HTML-escape it, which breaks the mermaid.js parser. Pre-extracting the block
    keeps the diagram source intact for client-side rendering.
    """

    def repl(m: re.Match) -> str:
        body = m.group(1)
        # markdown's md_in_html extension lets a raw <div> pass through if
        # surrounded by blank lines; the body is opaque (no markdown rendering).
        return f'\n<div class="mermaid">\n{body}\n</div>\n'

    return _MERMAID_RE.sub(repl, text)


def render_markdown(src: str) -> tuple[str, list[dict]]:
    """Convert markdown to HTML.

    Returns (html, headings) where headings is a list of
    {level, text, id} for h2 and h3 elements (used by the on-this-page TOC).
    """
    src = preprocess_mermaid(src)
    src = preprocess_admonitions(src)

    md = markdown.Markdown(
        extensions=[
            "extra",  # tables, fenced_code, attr_list, md_in_html, etc.
            "sane_lists",
            "smarty",
            "toc",
        ],
        extension_configs={
            "toc": {
                "permalink": False,
                "slugify": lambda v, _sep: slugify(v),
            },
        },
        output_format="html5",
    )
    html = md.convert(src)

    # Extract h2/h3 headings for the on-this-page TOC.
    headings: list[dict] = []
    for tok in getattr(md, "toc_tokens", []):
        # mkdir's toc tokens are nested; flatten h2/h3.
        _collect_headings(tok, headings, max_level=3)

    return html, headings


def _collect_headings(token: dict, out: list[dict], max_level: int) -> None:
    level = token.get("level", 0)
    if 2 <= level <= max_level:
        out.append(
            {
                "level": level,
                "text": token.get("name", "").strip(),
                "id": token.get("id", ""),
            }
        )
    for child in token.get("children", []) or []:
        _collect_headings(child, out, max_level)


def parse_front_matter(src: str) -> tuple[dict, str]:
    """Strip leading YAML front-matter and return (meta, body)."""
    if src.startswith("---\n"):
        end = src.find("\n---\n", 4)
        if end != -1:
            front = src[4:end]
            body = src[end + 5 :]
            try:
                meta = yaml.safe_load(front) or {}
            except yaml.YAMLError:
                meta = {}
            return meta, body
    return {}, src


# ---------------------------------------------------------------------- build


def js_string(value: str) -> str:
    """Encode a Python string for safe embedding in a JS object literal."""
    return json.dumps(value, ensure_ascii=False)


def build_language(lang: str, sections: list[Section], default_lang: str) -> tuple[dict, int, int]:
    """Render all pages for a single language. Returns (data, ok_count, fallback_count)."""
    pages_data: dict[str, dict] = {}
    ok = 0
    fallback = 0

    for sec in sections:
        for page in sec.pages:
            key = f"{sec.id}/{page.page_id}"
            src_path = SOURCE_DIR / lang / sec.id / f"{page.page_id}.md"

            used_fallback = False
            if not src_path.exists():
                # Fall back to default language so the page still appears.
                src_path = SOURCE_DIR / default_lang / sec.id / f"{page.page_id}.md"
                used_fallback = True

            if not src_path.exists():
                # Neither lang nor default has content — emit a placeholder.
                pages_data[key] = {
                    "html": "<p><em>This page is not yet written. Check back soon.</em></p>",
                    "headings": [],
                    "title": page.titles.get(lang) or page.titles.get(default_lang) or page.page_id,
                    "description": "",
                    "fallback": True,
                    "missing": True,
                }
                fallback += 1
                continue

            raw = src_path.read_text(encoding="utf-8")
            front, body = parse_front_matter(raw)
            html, headings = render_markdown(body)

            pages_data[key] = {
                "html": html,
                "headings": headings,
                "title": front.get("title") or page.titles.get(lang) or page.titles.get(default_lang) or page.page_id,
                "description": front.get("description", ""),
                "fallback": used_fallback,
                "missing": False,
            }
            if used_fallback:
                fallback += 1
            else:
                ok += 1

    return pages_data, ok, fallback


def serialise_data(pages: dict, lang: str) -> str:
    """Emit a JS module that registers the pages on window.ForgeLMUserManuals."""
    parts = [
        "/* AUTO-GENERATED by tools/build_usermanuals.py — do not edit by hand. */",
        "(function () {",
        "  'use strict';",
        "  var root = window.ForgeLMUserManuals = window.ForgeLMUserManuals || {};",
        f"  root[{js_string(lang)}] = {{",
    ]
    for key, page in sorted(pages.items()):
        parts.append(
            "    "
            + js_string(key)
            + ": {"
            + "title: "
            + js_string(page["title"])
            + ", "
            + "description: "
            + js_string(page["description"])
            + ", "
            + "html: "
            + js_string(page["html"])
            + ", "
            + "headings: "
            + json.dumps(page["headings"], ensure_ascii=False)
            + ", "
            + "fallback: "
            + ("true" if page["fallback"] else "false")
            + ", "
            + "missing: "
            + ("true" if page["missing"] else "false")
            + "},"
        )
    parts.append("  };")
    parts.append("})();")
    return "\n".join(parts) + "\n"


def serialise_index(sections: list[Section], languages: list[str]) -> str:
    """Emit the navigation structure (no per-page HTML), shared across langs."""
    nav = []
    for sec in sections:
        nav.append(
            {
                "id": sec.id,
                "icon": sec.icon,
                "titles": sec.titles,
                "pages": [{"id": p.page_id, "titles": p.titles} for p in sec.pages],
            }
        )
    payload = {
        "languages": languages,
        "sections": nav,
    }
    return (
        "/* AUTO-GENERATED by tools/build_usermanuals.py — do not edit by hand. */\n"
        "window.ForgeLMUserManualsIndex = " + json.dumps(payload, ensure_ascii=False, indent=2) + ";\n"
    )


# ---------------------------------------------------------------------- main


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify generated files match the current sources; exit 1 if stale.",
    )
    args = parser.parse_args()

    languages, sections = load_meta()
    default_lang = languages[0] if languages else "en"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    written: dict[Path, str] = {}

    # Per-language data files.
    for lang in languages:
        pages, ok, fb = build_language(lang, sections, default_lang)
        out_path = OUTPUT_DIR / f"{lang}.js"
        written[out_path] = serialise_data(pages, lang)
        marker = "✓" if fb == 0 else "fallbacks=" + str(fb)
        print(f"  {lang}: {ok} pages translated, {marker}")

    # Shared navigation index.
    index_path = OUTPUT_DIR / "_index.js"
    written[index_path] = serialise_index(sections, languages)

    if args.check:
        stale = []
        for path, content in written.items():
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                stale.append(path.relative_to(REPO_ROOT))
        if stale:
            print("\nstale generated files (run tools/build_usermanuals.py):")
            for s in stale:
                print(f"  - {s}")
            return 1
        print("\nall generated files are up to date.")
        return 0

    for path, content in written.items():
        path.write_text(content, encoding="utf-8")
        rel = path.relative_to(REPO_ROOT)
        print(f"  wrote {rel} ({len(content):,} bytes)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
