"""Tests for the focused-corpus lock (manifest hashes and tamper detection)."""
from pathlib import Path

import pytest

from dusnx_core import domain_corpus

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCKED_MANIFEST = REPO_ROOT / "datasets" / "domain_corpus_v1" / "manifest.json"


def write_corpus(root: Path) -> Path:
    (root / "docs").mkdir()
    (root / "docs" / "a.md").write_text("# Alpha\n\nnội dung A\n", encoding="utf-8")
    (root / "docs" / "b.md").write_text("# Beta\n\nnội dung B\n", encoding="utf-8")
    return root


def test_manifest_records_hashes_titles_and_totals(tmp_path):
    root = write_corpus(tmp_path)
    manifest = domain_corpus.build_manifest(
        ["docs/a.md", "docs/b.md"], "test-corpus", "kiểm thử", "2026-11-14T00:00:00Z", root=root)
    assert manifest["totals"]["documents"] == 2
    assert manifest["documents"][0]["title"] == "Alpha"
    assert len(manifest["documents"][0]["sha256"]) == 64
    assert domain_corpus.verify(manifest, root=root) == []


def test_verify_detects_an_edited_document(tmp_path):
    root = write_corpus(tmp_path)
    manifest = domain_corpus.build_manifest(
        ["docs/a.md", "docs/b.md"], "test-corpus", "kiểm thử", "2026-11-14T00:00:00Z", root=root)
    # Same length, different bytes: only the hash can catch this edit.
    (root / "docs" / "a.md").write_text("# Alpha\n\nnội dung X\n", encoding="utf-8")
    problems = domain_corpus.verify(manifest, root=root)
    assert any("sha256 mismatch" in problem for problem in problems)


def test_manifest_rejects_duplicates_and_paths_outside_the_root(tmp_path):
    root = write_corpus(tmp_path)
    with pytest.raises(ValueError):
        domain_corpus.build_manifest(
            ["docs/a.md", "docs/a.md"], "c", "d", "t", root=root)
    with pytest.raises(ValueError):
        domain_corpus.build_manifest(
            ["../outside.md"], "c", "d", "t", root=root)


def test_locked_repository_corpus_matches_its_manifest():
    manifest = domain_corpus.load_manifest(LOCKED_MANIFEST)
    assert 10 <= len(manifest["documents"]) <= 20
    assert domain_corpus.verify(manifest) == []
