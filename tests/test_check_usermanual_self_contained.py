"""Regression tests for ``tools/check_usermanual_self_contained.py``.

The guard blocks any link inside ``docs/usermanuals/`` that would
404 in the static-site SPA viewer:

- SPA hash-router routes (``#/<section>/<page>``) MUST back onto a
  real ``docs/usermanuals/<lang>/<section>/<page>.md`` file.
- Repo-relative paths MUST resolve under the same ``docs/usermanuals/<lang>/``
  language root — any traversal escaping it (e.g. ``../../../guides/foo.md``)
  is a violation.
- External HTTPS URLs and pure same-file anchors are skipped.
- Fenced code blocks are skipped (sample JSON / shell output that
  mentions ``docs/...`` paths as data must not count as a violation).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_TOOL_PATH = _REPO_ROOT / "tools" / "check_usermanual_self_contained.py"


def _load_tool() -> object:
    spec = importlib.util.spec_from_file_location("check_usermanual_self_contained", _TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_usermanual_self_contained"] = module
    spec.loader.exec_module(module)
    return module


def _build_manual_tree(root: Path) -> Path:
    """Create a minimal docs/usermanuals/en/ tree for fixture pages."""
    usermanuals = root / "docs" / "usermanuals"
    en_concepts = usermanuals / "en" / "concepts"
    en_concepts.mkdir(parents=True)
    (en_concepts / "alignment.md").write_text("# Alignment\n", encoding="utf-8")
    en_training = usermanuals / "en" / "training"
    en_training.mkdir(parents=True)
    (en_training / "sft.md").write_text("# SFT\n", encoding="utf-8")
    # An out-of-manual sibling so we can test escape-attempts.
    (root / "docs" / "guides").mkdir(parents=True)
    (root / "docs" / "guides" / "foo.md").write_text("# Foo\n", encoding="utf-8")
    return usermanuals


def _write_page(usermanuals: Path, lang: str, section: str, name: str, body: str) -> Path:
    path = usermanuals / lang / section / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# §1 — happy path: SPA routes that back onto real pages pass
# ---------------------------------------------------------------------------


class TestSpaRouteHappyPath:
    def test_valid_spa_route_passes(self, tmp_path: Path):
        tool = _load_tool()
        usermanuals = _build_manual_tree(tmp_path)
        _write_page(
            usermanuals,
            "en",
            "training",
            "pipelines",
            "# Pipelines\n\n- [SFT](#/training/sft)\n",
        )
        broken = tool._collect_broken(list(tool._walk_manual_files(usermanuals)), usermanuals)
        assert broken == []

    def test_external_url_passes(self, tmp_path: Path):
        tool = _load_tool()
        usermanuals = _build_manual_tree(tmp_path)
        _write_page(
            usermanuals,
            "en",
            "training",
            "pipelines",
            "# Pipelines\n\n- [GitHub](https://github.com/foo/bar)\n",
        )
        broken = tool._collect_broken(list(tool._walk_manual_files(usermanuals)), usermanuals)
        assert broken == []

    def test_pure_anchor_passes(self, tmp_path: Path):
        tool = _load_tool()
        usermanuals = _build_manual_tree(tmp_path)
        _write_page(
            usermanuals,
            "en",
            "training",
            "pipelines",
            "# Pipelines\n\n## A section\n\n[Top](#a-section)\n",
        )
        broken = tool._collect_broken(list(tool._walk_manual_files(usermanuals)), usermanuals)
        assert broken == []


# ---------------------------------------------------------------------------
# §2 — SPA route to a non-existent page is flagged
# ---------------------------------------------------------------------------


class TestSpaRouteBacking:
    def test_spa_route_missing_backing_file_fails(self, tmp_path: Path):
        tool = _load_tool()
        usermanuals = _build_manual_tree(tmp_path)
        _write_page(
            usermanuals,
            "en",
            "training",
            "pipelines",
            "# Pipelines\n\n[Ghost](#/standards/release)\n",
        )
        broken = tool._collect_broken(list(tool._walk_manual_files(usermanuals)), usermanuals)
        assert len(broken) == 1
        assert "#/standards/release" in broken[0].reason
        assert "no backing file" in broken[0].reason

    def test_spa_route_must_match_canonical_form(self, tmp_path: Path):
        # ``#/<section>`` without a page is not the canonical form.
        tool = _load_tool()
        usermanuals = _build_manual_tree(tmp_path)
        _write_page(
            usermanuals,
            "en",
            "training",
            "pipelines",
            "# Pipelines\n\n[Bare](#/training)\n",
        )
        broken = tool._collect_broken(list(tool._walk_manual_files(usermanuals)), usermanuals)
        assert len(broken) == 1
        assert "canonical" in broken[0].reason


# ---------------------------------------------------------------------------
# §3 — repo-relative paths escaping the language root are flagged
# ---------------------------------------------------------------------------


class TestRelativePathEscape:
    def test_three_up_repo_relative_path_flagged(self, tmp_path: Path):
        tool = _load_tool()
        usermanuals = _build_manual_tree(tmp_path)
        _write_page(
            usermanuals,
            "en",
            "training",
            "pipelines",
            "# Pipelines\n\n[Foo](../../../guides/foo.md)\n",
        )
        broken = tool._collect_broken(list(tool._walk_manual_files(usermanuals)), usermanuals)
        assert len(broken) == 1
        assert "escapes" in broken[0].reason
        # Error message must steer the author to the correct fix.
        assert "#/<section>/<page>" in broken[0].reason
        assert "github.com" in broken[0].reason

    def test_intra_manual_path_to_existing_sibling_section_flagged(self, tmp_path: Path):
        # The SPA does not intercept ``../section/page.md`` href clicks;
        # they 404 even when the file exists on disk.  The guard must
        # flag this AND suggest the SPA route as the replacement.
        tool = _load_tool()
        usermanuals = _build_manual_tree(tmp_path)
        _write_page(
            usermanuals,
            "en",
            "concepts",
            "intro",
            "# Intro\n\n[SFT](../training/sft.md)\n",
        )
        broken = tool._collect_broken(list(tool._walk_manual_files(usermanuals)), usermanuals)
        assert len(broken) == 1
        assert "intra-manual" in broken[0].reason
        # The error MUST point the author at the SPA-route fix.
        assert "#/training/sft" in broken[0].reason

    def test_intra_manual_path_to_missing_target_also_flagged(self, tmp_path: Path):
        # Doesn't matter whether the disk file exists — any ``.md``
        # relative href fires plain browser navigation in the SPA.
        tool = _load_tool()
        usermanuals = _build_manual_tree(tmp_path)
        _write_page(
            usermanuals,
            "en",
            "concepts",
            "intro",
            "# Intro\n\n[Bogus](../training/notreal.md)\n",
        )
        broken = tool._collect_broken(list(tool._walk_manual_files(usermanuals)), usermanuals)
        assert len(broken) == 1
        # Path resolves under the lang root, so it's flagged as the
        # intra-manual breakage (not the escape branch).
        assert "intra-manual" in broken[0].reason


# ---------------------------------------------------------------------------
# §4 — fenced code blocks are skipped (sample data is not a link)
# ---------------------------------------------------------------------------


class TestFencedCodeBlockSkip:
    def test_link_in_fenced_block_not_validated(self, tmp_path: Path):
        # A JSON sample / shell snippet may legitimately mention
        # ``docs/...`` paths as literal data.  Don't flag those.
        tool = _load_tool()
        usermanuals = _build_manual_tree(tmp_path)
        body = '# Page\n\nExample output:\n\n```json\n{"note": "See [foo](../../../guides/foo.md) for details."}\n```\n'
        _write_page(usermanuals, "en", "training", "pipelines", body)
        broken = tool._collect_broken(list(tool._walk_manual_files(usermanuals)), usermanuals)
        assert broken == []

    def test_tilde_fenced_block_also_skipped(self, tmp_path: Path):
        tool = _load_tool()
        usermanuals = _build_manual_tree(tmp_path)
        body = "# Page\n\n~~~text\n[bad](../../../guides/foo.md)\n~~~\n"
        _write_page(usermanuals, "en", "training", "pipelines", body)
        broken = tool._collect_broken(list(tool._walk_manual_files(usermanuals)), usermanuals)
        assert broken == []


# ---------------------------------------------------------------------------
# §5 — exit-code contract: strict flips return code, advisory exits 0
# ---------------------------------------------------------------------------


class TestExitContract:
    def test_strict_exits_one_on_violation(self, tmp_path: Path, monkeypatch, capsys):
        tool = _load_tool()
        usermanuals = _build_manual_tree(tmp_path)
        _write_page(
            usermanuals,
            "en",
            "training",
            "pipelines",
            "# Pipelines\n\n[Foo](../../../guides/foo.md)\n",
        )
        rc = tool.main(["--repo-root", str(tmp_path), "--strict"])
        assert rc == 1
        out = capsys.readouterr().out
        assert "FAIL" in out

    def test_advisory_exits_zero_on_violation(self, tmp_path: Path, capsys):
        tool = _load_tool()
        usermanuals = _build_manual_tree(tmp_path)
        _write_page(
            usermanuals,
            "en",
            "training",
            "pipelines",
            "# Pipelines\n\n[Foo](../../../guides/foo.md)\n",
        )
        rc = tool.main(["--repo-root", str(tmp_path)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "WARN" in out

    def test_clean_tree_returns_zero(self, tmp_path: Path, capsys):
        tool = _load_tool()
        usermanuals = _build_manual_tree(tmp_path)
        _write_page(
            usermanuals,
            "en",
            "training",
            "pipelines",
            "# Pipelines\n\n[SFT](#/training/sft)\n",
        )
        rc = tool.main(["--repo-root", str(tmp_path), "--strict"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "OK" in out

    def test_missing_usermanuals_dir_errors(self, tmp_path: Path, capsys):
        tool = _load_tool()
        rc = tool.main(["--repo-root", str(tmp_path), "--strict"])
        assert rc == 1
        err = capsys.readouterr().err
        assert "does not exist" in err


# ---------------------------------------------------------------------------
# §6 — SPA route with #anchor suffix: the viewer appends one via
#       history.replaceState when the reader clicks a TOC entry, so the
#       canonical route form MUST accept ``#/<section>/<page>#<heading>``
#       as long as the backing .md file exists.
# ---------------------------------------------------------------------------


class TestSpaRouteAnchorSuffix:
    def test_spa_route_with_anchor_passes_when_page_exists(self, tmp_path: Path):
        tool = _load_tool()
        usermanuals = _build_manual_tree(tmp_path)
        _write_page(
            usermanuals,
            "en",
            "training",
            "pipelines",
            "# Pipelines\n\n[SFT details](#/training/sft#hyperparameters)\n",
        )
        broken = tool._collect_broken(list(tool._walk_manual_files(usermanuals)), usermanuals)
        assert broken == []

    def test_spa_route_with_anchor_fails_when_page_missing(self, tmp_path: Path):
        tool = _load_tool()
        usermanuals = _build_manual_tree(tmp_path)
        _write_page(
            usermanuals,
            "en",
            "training",
            "pipelines",
            "# Pipelines\n\n[Ghost](#/standards/release#deprecation)\n",
        )
        broken = tool._collect_broken(list(tool._walk_manual_files(usermanuals)), usermanuals)
        assert len(broken) == 1
        assert "no backing file" in broken[0].reason


# ---------------------------------------------------------------------------
# §7 — Markdown link title parsing: ``[text](url "title")`` and
#       ``[text](url 'title')`` are valid CommonMark; the title is
#       presentational and must not be appended to the href.
# ---------------------------------------------------------------------------


class TestLinkTitleStripping:
    def test_spa_route_with_double_quoted_title_passes(self, tmp_path: Path):
        tool = _load_tool()
        usermanuals = _build_manual_tree(tmp_path)
        _write_page(
            usermanuals,
            "en",
            "training",
            "pipelines",
            '# Pipelines\n\n[SFT](#/training/sft "Supervised fine-tuning")\n',
        )
        broken = tool._collect_broken(list(tool._walk_manual_files(usermanuals)), usermanuals)
        assert broken == []

    def test_external_url_with_single_quoted_title_passes(self, tmp_path: Path):
        tool = _load_tool()
        usermanuals = _build_manual_tree(tmp_path)
        _write_page(
            usermanuals,
            "en",
            "training",
            "pipelines",
            "# Pipelines\n\n[GitHub](https://github.com/foo/bar 'repo home')\n",
        )
        broken = tool._collect_broken(list(tool._walk_manual_files(usermanuals)), usermanuals)
        assert broken == []
