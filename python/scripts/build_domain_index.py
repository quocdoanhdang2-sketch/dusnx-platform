#!/usr/bin/env python3
"""Build the focused domain index from the locked corpus manifest.

The index is a derived artifact and lives under runtime/, so it can be deleted
and rebuilt at any time without touching the repository-wide rag.db.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
PYTHON_DIR = HERE.parents[1]
ROOT = HERE.parents[2]
sys.path.insert(0, str(PYTHON_DIR))
sys.path.insert(0, str(PYTHON_DIR / "src"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from apps.ai_api import rag  # noqa: E402
from dusnx_core import domain_corpus  # noqa: E402

DEFAULT_MANIFEST = ROOT / "datasets" / "domain_corpus_v1" / "manifest.json"
DEFAULT_DB = ROOT / "runtime" / "domain-rag" / "rag-domain.db"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    manifest = domain_corpus.load_manifest(Path(args.manifest).resolve())
    problems = domain_corpus.verify(manifest)
    if problems:
        print(json.dumps({"status": "refused", "problems": problems},
                         ensure_ascii=False, indent=2))
        return 1

    os.environ["DUSNX_RAG_DB"] = str(Path(args.db).resolve())
    status = rag.build_index(
        force=args.force, paths=domain_corpus.document_paths(manifest))
    print(json.dumps({
        "status": "built",
        "corpus_id": manifest["corpus_id"],
        "domain": manifest["domain"],
        "manifest_documents": manifest["totals"]["documents"],
        **status,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
