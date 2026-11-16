#!/usr/bin/env python3
"""Create or verify the focused-corpus manifest.

Freezing the corpus is the first step of the domain-chatbot workflow: the
manifest decides which documents an index may read, and stores their hashes so
a later edit cannot silently change what the model was evaluated on.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
PYTHON_DIR = HERE.parents[1]
ROOT = HERE.parents[2]
sys.path.insert(0, str(PYTHON_DIR))
sys.path.insert(0, str(PYTHON_DIR / "src"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from dusnx_core import domain_corpus  # noqa: E402

DEFAULT_DIR = ROOT / "datasets" / "domain_corpus_v1"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", default=str(DEFAULT_DIR / "sources.txt"))
    parser.add_argument("--out", default=str(DEFAULT_DIR / "manifest.json"))
    parser.add_argument("--corpus-id", default="dusnx-ops-v1")
    parser.add_argument(
        "--domain", default="Vận hành, bảo mật và tích hợp nền tảng DUSN-X")
    parser.add_argument(
        "--check", action="store_true",
        help="verify the locked manifest instead of writing a new one")
    args = parser.parse_args()

    out = Path(args.out).resolve()
    if args.check:
        manifest = domain_corpus.load_manifest(out)
        problems = domain_corpus.verify(manifest)
        print(json.dumps({
            "status": "ok" if not problems else "failed",
            "corpus_id": manifest["corpus_id"],
            "documents": len(manifest["documents"]),
            "problems": problems,
        }, ensure_ascii=False, indent=2))
        return 0 if not problems else 1

    sources = domain_corpus.read_sources(Path(args.sources).resolve())
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    if out.exists():
        # Keep the original freeze date when re-locking an unchanged corpus.
        try:
            created_at = domain_corpus.load_manifest(out)["created_at"]
        except (ValueError, json.JSONDecodeError, KeyError):
            pass
    manifest = domain_corpus.build_manifest(
        sources, args.corpus_id, args.domain, created_at)
    digest = hashlib.sha256(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    manifest["manifest_sha256"] = digest
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "written",
        "path": str(out),
        "corpus_id": manifest["corpus_id"],
        "documents": manifest["totals"]["documents"],
        "bytes": manifest["totals"]["bytes"],
        "manifest_sha256": digest,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
