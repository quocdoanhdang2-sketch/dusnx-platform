"""Read-only 90/30-day inventory. No deletion, purge, VACUUM or apply mode exists."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3


def inventory(database: Path, cutoff: str) -> dict:
    if not database.is_file():
        return {"status": "missing_database", "complete": False}
    # Opening with mode=ro refuses a missing DB rather than creating an empty one.
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        counts = {}
        # Fixed identifiers only; no SQL identifiers come from command arguments.
        for table, column in (("chat_messages", "created_at"), ("user_events", "created_at")):
            if table not in tables:
                counts[table] = {"status": "missing_table"}
                continue
            row = db.execute(f"""SELECT COUNT(*),
                COALESCE(SUM(julianday({column}) < julianday(?)),0),
                COALESCE(SUM(julianday({column}) IS NULL),0)
                FROM {table}""", (cutoff,)).fetchone()
            counts[table] = {"total": row[0], "older_than_cutoff": row[1], "invalid_timestamp": row[2],
                             "age_basis": column, "status": "inventoried"}
        excluded = sorted(tables - {"chat_messages", "user_events"})
        return {"status": "read_only_inventory", "tables": counts, "excluded_tables": excluded,
                "complete": all(x.get("status") == "inventoried" and x["invalid_timestamp"] == 0
                                for x in counts.values())}


def backup_inventory(directory: Path | None, cutoff: datetime) -> dict:
    if directory is None or not directory.is_dir():
        return {"status": "not_inspected", "complete": False}
    # Do not recurse into arbitrary backups, parse contents or follow symlinks.
    files = [p for p in directory.iterdir() if not p.is_symlink() and p.is_file()]
    old = [p for p in files if datetime.fromtimestamp(p.stat().st_mtime, timezone.utc) < cutoff]
    return {"status": "mtime_estimate_only", "complete": False,
            "direct_regular_files": len(files), "older_than_cutoff_estimate": len(old),
            "older_bytes_estimate": sum(p.stat().st_size for p in old),
            "nested_directories": sum(p.is_dir() for p in directory.iterdir() if not p.is_symlink()),
            "warning": "mtime is not a verified backup creation date; nested backups/legal holds not evaluated"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--as-of", help="Timezone-aware ISO timestamp; default current UTC")
    args = parser.parse_args()
    now = datetime.fromisoformat(args.as_of.replace("Z", "+00:00")) if args.as_of else datetime.now(timezone.utc)
    if now.tzinfo is None:
        parser.error("--as-of must include a timezone")
    now = now.astimezone(timezone.utc)
    cutoff = now - timedelta(days=90)
    report = {"status": "dry_run_only", "as_of_utc": now.isoformat(),
              "policy": {"chat_event_days": 90, "backup_days": 30,
                         "event_age_basis": "server created_at, not client-supplied event_time_utc",
                         "apply_requires_user_review": True},
              "deletion_performed": False, "apply_supported": False,
              "chat_event_cutoff_exclusive": cutoff.isoformat(),
              "memory_db": inventory(args.data_dir / "memory.db", cutoff.isoformat()),
              "backups": backup_inventory(args.backup_dir, now - timedelta(days=30)),
              "unresolved_before_apply": [
                  "chat_receipts contain copied response data but have no creation timestamp",
                  "memory versions, pending decisions, session titles and hidden state are not covered by this age policy",
                  "legacy Gateway JSON state/events and external logs require separate inventory",
                  "account purge, legal holds and deletion from backup generations are not implemented",
                  "do not apply an age-based deletion or restore old data without an approved lifecycle policy"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Refuse overwriting an earlier review artifact or a source DB by mistake.
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
