"""Focused-corpus manifest: the scope a domain chatbot is allowed to read.

The corpus is a scope, not a copy. Documents stay at their repository paths so
runbooks keep one source of truth; the manifest freezes exactly which files an
index may read and what their content hash was when it was frozen.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Iterable

MANIFEST_VERSION = "1"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _title(text: str, fallback: str) -> str:
    for line in text.splitlines():
        match = re.match(r"^#\s+(.+?)\s*$", line)
        if match:
            return match.group(1)
    return fallback.replace("_", " ")


def build_manifest(sources: Iterable[str], corpus_id: str, domain: str,
                   created_at: str, root: Path | None = None) -> dict:
    root = (root or repo_root()).resolve()
    documents: list[dict] = []
    seen: set[str] = set()
    for ordinal, raw in enumerate(sources, 1):
        relative = raw.strip()
        if not relative:
            continue
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"source escapes repository root: {relative}") from exc
        if relative in seen:
            raise ValueError(f"duplicate source: {relative}")
        if not path.is_file():
            raise FileNotFoundError(relative)
        seen.add(relative)
        text = path.read_text(encoding="utf-8", errors="replace")
        documents.append({
            "id": f"doc-{ordinal:02d}",
            "path": Path(relative).as_posix(),
            "sha256": sha256_file(path),
            "bytes": path.stat().st_size,
            "title": _title(text, path.stem),
        })
    if not documents:
        raise ValueError("corpus needs at least one document")
    return {
        "manifest_version": MANIFEST_VERSION,
        "corpus_id": corpus_id,
        "domain": domain,
        "created_at": created_at,
        "documents": documents,
        "totals": {
            "documents": len(documents),
            "bytes": sum(doc["bytes"] for doc in documents),
        },
    }


def read_sources(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines
            if line.strip() and not line.lstrip().startswith("#")]


def load_manifest(path: Path) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("manifest_version") != MANIFEST_VERSION:
        raise ValueError(f"unsupported manifest_version: {manifest.get('manifest_version')}")
    documents = manifest.get("documents")
    if not isinstance(documents, list) or not documents:
        raise ValueError("manifest has no documents")
    paths = [doc["path"] for doc in documents]
    if len(paths) != len(set(paths)):
        raise ValueError("manifest repeats a document path")
    return manifest


def verify(manifest: dict, root: Path | None = None) -> list[str]:
    root = (root or repo_root()).resolve()
    problems: list[str] = []
    for doc in manifest["documents"]:
        path = (root / doc["path"]).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            problems.append(f"{doc['id']} {doc['path']}: escapes repository root")
            continue
        if not path.is_file():
            problems.append(f"{doc['id']} {doc['path']}: missing")
            continue
        if path.stat().st_size == doc["bytes"] and sha256_file(path) == doc["sha256"]:
            continue
        # Cross-platform line ending normalization (CRLF <-> LF) for git checkouts
        try:
            raw = path.read_bytes()
        except OSError as exc:
            problems.append(f"{doc['id']} {doc['path']}: read error ({exc})")
            continue

        crlf_variant = raw.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        if len(crlf_variant) == doc["bytes"] and hashlib.sha256(crlf_variant).hexdigest() == doc["sha256"]:
            continue
        lf_variant = raw.replace(b"\r\n", b"\n")
        if len(lf_variant) == doc["bytes"] and hashlib.sha256(lf_variant).hexdigest() == doc["sha256"]:
            continue

        if path.stat().st_size != doc["bytes"]:
            problems.append(f"{doc['id']} {doc['path']}: size changed")
            continue
        if sha256_file(path) != doc["sha256"]:
            problems.append(f"{doc['id']} {doc['path']}: sha256 mismatch")
    return problems


def document_paths(manifest: dict) -> list[str]:
    return [doc["path"] for doc in manifest["documents"]]
