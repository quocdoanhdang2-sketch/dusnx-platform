#!/usr/bin/env python3
"""Encode stored chat sessions into typed, content-free signal records."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
PYTHON_DIR = HERE.parents[1]
ROOT = HERE.parents[2]
sys.path.insert(0, str(PYTHON_DIR))
sys.path.insert(0, str(PYTHON_DIR / "src"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from dusnx_core import session_signal  # noqa: E402

DEFAULT_DB = ROOT / "python" / "data" / "memory.db"


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def load_session(conn: sqlite3.Connection, session_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT role, content FROM chat_messages WHERE session_id=? ORDER BY created_at",
        (session_id,)).fetchall()
    return [{"role": row["role"], "content": row["content"]} for row in rows]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--session")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--out", help="optional JSONL output path")
    args = parser.parse_args()

    conn = connect(Path(args.db).resolve())
    if args.session:
        session_ids = [args.session]
    else:
        session_ids = [row[0] for row in conn.execute(
            "SELECT session_id FROM chat_sessions ORDER BY updated_at DESC LIMIT ?",
            (args.limit,)).fetchall()]

    records = []
    for session_id in session_ids:
        messages = load_session(conn, session_id)
        if not messages:
            continue
        signal = session_signal.encode_session(messages)
        record = signal.as_record(session_id=hashlib.sha256(
            session_id.encode("utf-8")).hexdigest()[:16])
        records.append(record)

    summary = {
        "sessions": len(records),
        "turns": sum(record["turn_count"] for record in records),
        "intents": {},
        "outcomes": {},
        "with_correction": sum(1 for record in records if record["has_correction"]),
        "with_memory_write": sum(1 for record in records if record["has_memory_write"]),
    }
    for record in records:
        for key, value in record["intents"].items():
            summary["intents"][key] = summary["intents"].get(key, 0) + value
        for key, value in record["outcomes"].items():
            summary["outcomes"][key] = summary["outcomes"].get(key, 0) + value

    if args.out:
        out = Path(args.out).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
                       encoding="utf-8")
        summary["out"] = str(out)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
