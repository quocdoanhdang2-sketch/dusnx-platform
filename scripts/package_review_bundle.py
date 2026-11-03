"""Export a committed review snapshot; never invent remote, CI or test outcomes.

Only approved text files from the commit are included. High-confidence credential
patterns are rejected; this limited scan is not a guarantee against all secrets.
Historical evidence stays historical and is not attributed to the exported HEAD.
"""
import argparse
import hashlib
import json
import re
import subprocess
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_COMMIT = "d11d4b3da51fd223b0c67e782ca5afb403def215"
ALLOWED_ROOTS = {"docs", "scripts", "python", "web-ui", "gateway-dotnet",
                 "gateway-dotnet.tests", "powerpoint-addin", ".github"}
ALLOWED_SUFFIXES = {".py", ".js", ".css", ".html", ".md", ".json", ".yml",
                    ".yaml", ".ps1", ".psm1", ".xml", ".toml", ".txt", ".cs", ".csproj"}
SECRET_PATTERN = re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----|github_pat_[A-Za-z0-9_]{30,}|ghp_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9]{30,}")


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.PIPE)


def checked_path(name):
    path = PurePosixPath(name)
    if (path.is_absolute() or ".." in path.parts or not path.parts
            or path.parts[0] not in ALLOWED_ROOTS | {"README.md"}
            or path.suffix.lower() not in ALLOWED_SUFFIXES
            or any(part.lower().startswith(".env") for part in path.parts)
            or "holdout" in path.name.lower()):
        raise ValueError(f"File outside the review allowlist: {name}")
    return path.as_posix()


def scan(data, name):
    if b"\0" in data or SECRET_PATTERN.search(data):
        raise ValueError(f"Binary content or credential pattern in: {name}")


def build_package(root=REPO_ROOT, baseline=BASELINE_COMMIT, output=None, verify_remote=False):
    root = Path(root).resolve()
    # Reject uncommitted tracked/untracked work instead of combining it with HEAD.
    if git(root, "status", "--porcelain", "--untracked-files=all").strip():
        raise ValueError("Working tree is dirty. Commit reviewed changes before packaging.")
    head = git(root, "rev-parse", "HEAD").decode().strip()
    base = git(root, "rev-parse", "--verify", baseline + "^{commit}").decode().strip()
    branch = git(root, "branch", "--show-current").decode().strip()
    if output is None:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        output = root / "runtime" / f"review-{head[:12]}-{stamp}.zip"
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError("Output already exists; choose a new ZIP path.")
    names = git(root, "diff", "--name-only", "--diff-filter=ACMRT", "-z", base, head).decode().split("\0")
    changed = [checked_path(name) for name in names if name]
    # Validate deleted paths too: the patch must not smuggle disallowed material.
    for name in git(root, "diff", "--name-only", "-z", base, head).decode().split("\0"):
        if name:
            checked_path(name)
    payload = {"changes.patch": git(root, "diff", "--binary", base, head)}
    for name in changed:
        payload["src/" + name] = git(root, "show", head + ":" + name)
    for name, data in payload.items():
        scan(data, name)
    remote = {"status": "not_checked", "sha": None, "matches_head": None}
    if verify_remote and branch:
        try:
            rows = git(root, "ls-remote", "origin", "refs/heads/" + branch).decode().splitlines()
            remote_sha = rows[0].split()[0] if rows else None
            remote = {"status": "checked", "sha": remote_sha, "matches_head": remote_sha == head}
        except subprocess.CalledProcessError:
            remote["status"] = "unavailable"
    summary = f"""# Review snapshot

Branch: {branch or '(detached)'}
Baseline: {base}
Commit exported: {head}
Source: git objects at this commit; not a copy of the working tree.
Remote observation: {json.dumps(remote)}
CI: not_checked. No CI or test result is inferred from packaging or push.
Evidence in src/docs is committed historical evidence, not a new execution.
No runtime directory, private DB, checkpoint or browser storage is included.
The credential scan checks selected patterns only; human review is still needed.
"""
    payload["REVIEW_SUMMARY.md"] = summary.encode()
    manifest = {
        "manifest_version": 2, "created_at_utc": datetime.now(UTC).isoformat(),
        "baseline_commit": base, "head_commit": head, "branch": branch,
        "working_tree_clean": True, "remote": remote, "ci": {"status": "not_checked"},
        "test_execution": {"status": "not_run_by_packager"},
        "artifacts": {name: {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}
                      for name, data in payload.items()},
    }
    payload["manifest.json"] = json.dumps(manifest, indent=2).encode()
    # Recheck after reads, including HEAD, before producing the snapshot.
    if (git(root, "rev-parse", "HEAD").decode().strip() != head
            or git(root, "status", "--porcelain", "--untracked-files=all").strip()):
        raise ValueError("Repository changed during packaging; retry from a stable checkout.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", zipfile.ZIP_DEFLATED) as archive:
        for name, data in payload.items():
            archive.writestr(name, data)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(json.dumps({"zip": str(output), "sha256": digest, "commit": head,
                      "remote": remote, "size_bytes": output.stat().st_size}))
    return output, digest, output.stat().st_size


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default=BASELINE_COMMIT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-remote", action="store_true")
    args = parser.parse_args()
    build_package(baseline=args.baseline, output=args.output, verify_remote=args.verify_remote)
