"""Regression guards for strict acceptance and version-correct review exports."""
import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import package_review_bundle as bundle
import verify_bilingual_generation as bilingual


@pytest.mark.parametrize("field,value", [
    ("provider_called", False), ("provider_ok", False), ("provider_used", "mock"),
    ("model_used", "wrong-model"), ("response_source", "grounded_template"), ("reply", " "),
])
def test_generation_contract_rejects_false_positive(field, value):
    response = {"provider_called": True, "provider_ok": True, "provider_used": "ollama",
                "model_used": "qwen2.5:0.5b", "response_source": "llm", "reply": "A real response"}
    assert bilingual.generation_contract(response)
    response[field] = value
    assert not bilingual.generation_contract(response)


@pytest.mark.parametrize("failed,divergent,uncertain,flags,options,expected", [
    (1, 0, 0, 0, [], 1),
    (0, 1, 0, 0, [], 0),
    (0, 1, 0, 0, ["--strict-language"], 1),
    (0, 0, 1, 0, ["--strict-language"], 1),
    (0, 0, 0, 1, ["--strict-quality"], 1),
    (0, 0, 0, 0, ["--strict-language", "--strict-quality"], 0),
])
def test_cli_exit_code(monkeypatch, tmp_path, failed, divergent, uncertain, flags, options, expected):
    summary = {"contract_failed": failed, "linguistic_divergent": divergent,
               "linguistic_uncertain": uncertain, "quality_flagged_cases": flags}
    monkeypatch.setattr(bilingual, "run_evaluation", lambda *args: {"summary": summary})
    monkeypatch.setattr(sys, "argv", ["verify", "--gateway", "http://127.0.0.1:9",
                                    "--output-dir", str(tmp_path / "result"), *options])
    with pytest.raises(SystemExit) as exc:
        bilingual.main()
    assert exc.value.code == expected


def test_repeated_output_is_not_a_quality_pass():
    text = "\n".join(f"{i}. Tái tạo và phân phối dữ liệu" for i in range(1, 15))
    assert bilingual.quality_flags(text) == ["repeated_lines"]
    summary = bilingual.compute_bilingual_summary({"case": {
        "case_type": "llm_generation", "contract_passed": True,
        "linguistic_status": "matched", "quality_flags": bilingual.quality_flags(text)}})
    assert summary["linguistic_matched"] == 1
    assert summary["quality_flagged_cases"] == 1
    assert bilingual.evaluation_exit_code(summary, strict_quality=True) == 1


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.PIPE).decode().strip()
    git("init")
    git("config", "user.name", "Test Reviewer")
    git("config", "user.email", "reviewer@example.invalid")
    (root / "README.md").write_text("baseline\n")
    git("add", "README.md")
    git("commit", "-m", "baseline")
    base = git("rev-parse", "HEAD")
    (root / "scripts").mkdir()
    source = root / "scripts" / "example.py"
    source.write_text("print('committed source')\n")
    git("add", "scripts/example.py")
    git("commit", "-m", "source")
    return root, base, git


def test_bundle_contains_committed_source_and_verified_hashes(repository, tmp_path):
    root, base, git = repository
    output, digest, _ = bundle.build_package(root, base, tmp_path / "review.zip")
    assert hashlib.sha256(output.read_bytes()).hexdigest() == digest
    with zipfile.ZipFile(output) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["head_commit"] == git("rev-parse", "HEAD")
        assert manifest["remote"]["status"] == "not_checked"
        assert manifest["ci"]["status"] == "not_checked"
        for name, metadata in manifest["artifacts"].items():
            assert hashlib.sha256(archive.read(name)).hexdigest() == metadata["sha256"]
        assert archive.read("src/scripts/example.py").decode() == "print('committed source')\n"
    with pytest.raises(FileExistsError):
        bundle.build_package(root, base, output)


def test_bundle_refuses_dirty_checkout(repository, tmp_path):
    root, base, _ = repository
    (root / "scripts/example.py").write_text("print('uncommitted changes')\n")
    with pytest.raises(ValueError, match="dirty"):
        bundle.build_package(root, base, tmp_path / "review.zip")
    assert not (tmp_path / "review.zip").exists()


def test_bundle_refuses_sensitive_tracked_file(repository, tmp_path):
    root, base, git = repository
    (root / ".env").write_text("SYNTHETIC_SETTING=example\n")
    git("add", ".env")
    git("commit", "-m", "synthetic forbidden file")
    with pytest.raises(ValueError, match="allowlist"):
        bundle.build_package(root, base, tmp_path / "review.zip")


def test_bundle_rejects_credential_pattern(repository, tmp_path):
    root, base, git = repository
    (root / "scripts/example.py").write_text("credential = '" + "ghp_" + "A" * 36 + "'\n")
    git("add", "scripts/example.py")
    git("commit", "-m", "synthetic scanner fixture")
    with pytest.raises(ValueError, match="credential pattern"):
        bundle.build_package(root, base, tmp_path / "review.zip")


def test_remote_mismatch_is_recorded_not_claimed_as_verified(repository, tmp_path, monkeypatch):
    root, base, _ = repository
    original = bundle.git
    def read_git(root, *args):
        if args[0] == "ls-remote":
            return (("0" * 40) + "\trefs/heads/test\n").encode()
        return original(root, *args)
    monkeypatch.setattr(bundle, "git", read_git)
    output, _, _ = bundle.build_package(root, base, tmp_path / "review.zip", verify_remote=True)
    with zipfile.ZipFile(output) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["remote"]["matches_head"] is False
        assert manifest["ci"]["status"] == "not_checked"


def test_failed_generation_does_not_count_error_text_as_language_success():
    summary = bilingual.compute_bilingual_summary({"bad": {
        "case_type": "llm_generation", "contract_passed": False,
        "linguistic_status": "matched"}})
    assert summary["contract_failed"] == 1
    assert summary["eligible_language_cases"] == 0
    assert summary["linguistic_matched"] == 0
