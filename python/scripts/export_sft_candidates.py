#!/usr/bin/env python3
"""Export real work sessions as SFT candidates, pending human review.

Nothing here is training data yet. The exporter reads the chat database
read-only, removes secrets and personal identifiers, encodes each session, and
writes candidates plus an empty review queue. A human must approve rows before
they can enter a locked dataset.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
import sys
from datetime import date
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
DEFAULT_OUT = ROOT / "runtime" / f"sft-candidates-{date.today().strftime('%Y%m%d')}"

README = """# SFT candidates (pending review)

These rows come from real chat sessions and are **not** training data.

- `candidates.jsonl` — one reviewed-candidate record per session. Message text
  is scrubbed for secrets, e-mail addresses and long hashes; `signal` is the
  deterministic encoding, not model output.
- `review_queue.csv` — one row per candidate. Fill `decision` with `keep`,
  `edit` or `drop`, then add a short `notes` reason. Only `keep`/`edit` rows may
  enter a locked dataset, and edited text must be reviewed again.

Rules:

1. Do not copy these files outside the machine, and never commit them.
2. Do not promote a dataset built from this queue without the evaluation gate
   in `docs/TRAINING_POLICY.md`.
3. Re-export after new sessions; candidate ids are stable per session.
"""


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT))
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--min-turns", type=int, default=2)
    parser.add_argument("--max-turns", type=int, default=16)
    parser.add_argument(
        "--require-signal",
        choices=["any", "correction", "memory_write", "correction_or_memory"],
        default="any",
        help="Filter candidates requiring specific interaction signals",
    )
    args = parser.parse_args()

    conn = connect(Path(args.db).resolve())
    sessions = conn.execute(
        "SELECT session_id FROM chat_sessions ORDER BY updated_at DESC LIMIT ?",
        (args.limit,)).fetchall()

    candidates = []
    stats = {"sessions_scanned": len(sessions), "kept": 0, "dropped_short": 0,
             "dropped_long": 0, "dropped_no_pair": 0, "dropped_empty": 0, "pairs": 0}
    intents: dict[str, int] = {}
    outcomes: dict[str, int] = {}

    for row in sessions:
        session_id = row["session_id"]
        messages = conn.execute(
            "SELECT role, content FROM chat_messages WHERE session_id=? ORDER BY created_at",
            (session_id,)).fetchall()
        if len(messages) < args.min_turns:
            stats["dropped_short"] += 1
            continue
        if len(messages) > args.max_turns:
            stats["dropped_long"] += 1
            continue
        roles = {message["role"] for message in messages}
        if not {"user", "assistant"}.issubset(roles):
            stats["dropped_no_pair"] += 1
            continue

        cleaned = [{"role": message["role"], "content": session_signal.scrub(message["content"] or "")}
                   for message in messages]
        cleaned = [message for message in cleaned if message["content"].strip()]
        if len(cleaned) < args.min_turns or not {"user", "assistant"}.issubset(
                {message["role"] for message in cleaned}):
            stats["dropped_empty"] += 1
            continue

        signal = session_signal.encode_session(cleaned)
        record_signal = signal.as_record()

        # Signal filtering if required by training policy
        if args.require_signal == "correction" and not signal.has_correction:
            continue
        if args.require_signal == "memory_write" and not signal.has_memory_write:
            continue
        if args.require_signal == "correction_or_memory" and not (signal.has_correction or signal.has_memory_write):
            continue

        candidate_id = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:16]
        candidates.append({
            "id": candidate_id,
            "session_id": candidate_id,
            "messages": cleaned,
            "signal": record_signal,
            "review_status": "pending",
            "source": "real_session",
        })
        stats["kept"] += 1
        stats["pairs"] += sum(1 for index, message in enumerate(cleaned)
                              if message["role"] == "assistant"
                              and index and cleaned[index - 1]["role"] == "user")
        for key, value in record_signal["intents"].items():
            intents[key] = intents.get(key, 0) + value
        for key, value in record_signal["outcomes"].items():
            outcomes[key] = outcomes.get(key, 0) + value

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "candidates.jsonl").write_text(
        "".join(json.dumps(candidate, ensure_ascii=False) + "\n" for candidate in candidates),
        encoding="utf-8")

    # Strict RFC 4180 CSV export using csv.writer to avoid broken columns
    with (out_dir / "review_queue.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["candidate_id", "turns", "intents", "outcomes", "decision", "notes"])
        for candidate in candidates:
            sig = candidate["signal"]
            writer.writerow([
                candidate["id"],
                sig["turn_count"],
                json.dumps(sig["intents"], ensure_ascii=False),
                json.dumps(sig["outcomes"], ensure_ascii=False),
                "",
                "",
            ])

    (out_dir / "README.md").write_text(README, encoding="utf-8")

    print(json.dumps({
        "status": "exported",
        "out_dir": str(out_dir),
        **stats,
        "intents": dict(sorted(intents.items())),
        "outcomes": dict(sorted(outcomes.items())),
        "review_status": "pending",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
