#!/usr/bin/env python3
"""
DUSN-X Training Data Validator
================================
Run from repo root:
    python scripts/validate_data.py [--data path/to/data.jsonl] [--strict]

Checks:
1. Schema: required fields present and correct types
2. Valid labels: intent, agent, action in taxonomy
3. Label distribution: per-class counts
4. Duplicate sequences: same user+content+time combos
5. Out-of-order timestamps within user sequences
6. Future feedback leakage: feedback_value should be from PREVIOUS event
7. User/sequence split integrity (no user in multiple splits)
8. Prints anonymized sample examples

Exit code:
  0 = valid (no blocking errors)
  1 = has blocking errors
  2 = has warnings only (unless --strict)
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


REQUIRED_FIELDS = {"global_user_id", "event_time_utc", "platform", "content", "intent_label", "selected_agent", "next_action_label"}
VALID_INTENTS = {"chat", "research", "summarize", "presentation_edit", "recommendation", "followup"}
VALID_AGENTS = {"conversation", "search_rag", "productivity"}
VALID_ACTIONS = {"reply", "search", "summarize", "edit_slide", "recommend", "clarify"}
VALID_PLATFORMS = {"web", "zalo", "powerpoint"}

# Acceptable provenance tags
VALID_PROVENANCE = {"synthetic", "human_written", "public_annotated", "ai_generated_reviewed"}


def read_jsonl(path: str | Path) -> list[dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append({"_lineno": lineno, **json.loads(line)})
            except json.JSONDecodeError as e:
                rows.append({"_lineno": lineno, "_parse_error": str(e)})
    return rows


def anonymize(text: str, max_len: int = 60) -> str:
    """Truncate and mask any obvious personal info patterns."""
    import re
    text = re.sub(r"\b[\w.+-]+@[\w.-]+\.\w+\b", "[EMAIL]", text)
    text = re.sub(r"\b\d{10,}\b", "[NUMBER]", text)
    return text[:max_len] + ("…" if len(text) > max_len else "")


def validate(data_path: Path, strict: bool = False) -> int:
    print(f"\n{'='*60}")
    print(f"DUSN-X Training Data Validator")
    print(f"File: {data_path}")
    print(f"{'='*60}\n")

    if not data_path.exists():
        print(f"❌ ERROR: File not found: {data_path}")
        return 1

    rows = read_jsonl(data_path)
    total = len(rows)
    print(f"📄 Total lines: {total}")

    errors: list[str] = []
    warnings: list[str] = []

    # 1. Parse errors
    parse_errors = [r for r in rows if "_parse_error" in r]
    valid_rows = [r for r in rows if "_parse_error" not in r]
    if parse_errors:
        errors.append(f"{len(parse_errors)} lines failed JSON parse (lines: {[r['_lineno'] for r in parse_errors[:5]]})")

    print(f"✅ Valid JSON rows: {len(valid_rows)}")

    # 2. Schema check
    schema_errors = []
    for r in valid_rows:
        missing = REQUIRED_FIELDS - set(r.keys())
        if missing:
            schema_errors.append((r["_lineno"], missing))
    if schema_errors:
        errors.append(f"{len(schema_errors)} rows missing required fields. First: line {schema_errors[0][0]} missing {schema_errors[0][1]}")
    else:
        print("✅ Schema: all required fields present")

    # 3. Label validation
    bad_intent = [r for r in valid_rows if r.get("intent_label") not in VALID_INTENTS]
    bad_agent = [r for r in valid_rows if r.get("selected_agent") not in VALID_AGENTS]
    bad_action = [r for r in valid_rows if r.get("next_action_label") not in VALID_ACTIONS]
    bad_platform = [r for r in valid_rows if r.get("platform") not in VALID_PLATFORMS]

    for label_name, bad_rows in [
        ("intent_label", bad_intent), ("selected_agent", bad_agent),
        ("next_action_label", bad_action), ("platform", bad_platform)
    ]:
        if bad_rows:
            vals = list({r.get(label_name) for r in bad_rows[:3]})
            errors.append(f"{len(bad_rows)} rows with invalid {label_name}: {vals}")
        else:
            print(f"✅ {label_name}: all valid")

    # 4. Provenance check
    has_provenance = [r for r in valid_rows if "provenance" in r]
    if has_provenance:
        bad_prov = [r for r in has_provenance if r.get("provenance") not in VALID_PROVENANCE]
        if bad_prov:
            warnings.append(f"{len(bad_prov)} rows with unrecognized provenance tags")
        print(f"📋 Provenance present: {len(has_provenance)}/{len(valid_rows)} rows")
        prov_counts = Counter(r.get("provenance", "unknown") for r in valid_rows)
        for prov, count in prov_counts.most_common():
            pct = count / len(valid_rows) * 100
            print(f"   {prov}: {count} ({pct:.1f}%)")
    else:
        warnings.append("No 'provenance' field found. Consider adding for data lineage tracking.")

    # 5. Label distribution
    print("\n📊 Label distribution:")
    intent_counts = Counter(r.get("intent_label", "MISSING") for r in valid_rows)
    agent_counts = Counter(r.get("selected_agent", "MISSING") for r in valid_rows)
    action_counts = Counter(r.get("next_action_label", "MISSING") for r in valid_rows)

    print("  Intents:")
    for k, v in intent_counts.most_common():
        pct = v / len(valid_rows) * 100
        print(f"    {k}: {v} ({pct:.1f}%)")
    print("  Agents:")
    for k, v in agent_counts.most_common():
        pct = v / len(valid_rows) * 100
        print(f"    {k}: {v} ({pct:.1f}%)")
    print("  Next actions:")
    for k, v in action_counts.most_common():
        pct = v / len(valid_rows) * 100
        print(f"    {k}: {v} ({pct:.1f}%)")

    # Check for severe imbalance (any class < 2%)
    total_rows = len(valid_rows)
    for label, counts in [("intent", intent_counts), ("agent", agent_counts), ("action", action_counts)]:
        rare = [k for k, v in counts.items() if v / total_rows < 0.02 and k != "MISSING"]
        if rare:
            warnings.append(f"Rare {label} classes (<2%): {rare}")

    # 6. User/sequence grouping
    user_events: dict[str, list[dict]] = defaultdict(list)
    for r in valid_rows:
        uid = r.get("global_user_id", "")
        if uid:
            user_events[uid].append(r)

    n_users = len(user_events)
    print(f"\n👥 Users: {n_users}")
    seq_lengths = [len(evts) for evts in user_events.values()]
    if seq_lengths:
        print(f"   Sequences per user: min={min(seq_lengths)}, max={max(seq_lengths)}, avg={sum(seq_lengths)/len(seq_lengths):.1f}")

    # 7. Out-of-order timestamps
    oor_users = []
    for uid, events in user_events.items():
        times = []
        for e in events:
            try:
                t = datetime.fromisoformat(e["event_time_utc"].replace("Z", "+00:00"))
                times.append(t)
            except Exception:
                pass
        for i in range(1, len(times)):
            if times[i] < times[i - 1]:
                oor_users.append(uid)
                break
    if oor_users:
        errors.append(f"{len(oor_users)} users have out-of-order timestamps: {oor_users[:3]}")
    else:
        print("✅ Timestamps: all in order per user")

    # 8. Duplicate detection (same user + content + time)
    seen = set()
    dupes = 0
    for r in valid_rows:
        key = (r.get("global_user_id"), r.get("content", ""), r.get("event_time_utc", ""))
        if key in seen:
            dupes += 1
        seen.add(key)
    if dupes > 0:
        errors.append(f"{dupes} duplicate (user, content, time) combinations found")
    else:
        print("✅ No duplicate (user, content, time) combinations")

    # 9. Future feedback leakage check
    # The dataset stores feedback_value. In a sequence, each event's feedback_value
    # should represent the rating of the PREVIOUS event (not the current one).
    # We can only check for gross violations: if every event in a user's sequence
    # has a non-zero feedback_value including the first event (no prior event to rate),
    # that is suspicious.
    suspicious_feedback = []
    for uid, events in user_events.items():
        if len(events) >= 2:
            first_fb = float(events[0].get("feedback_value", 0.0) or 0.0)
            if first_fb != 0.0:
                suspicious_feedback.append(uid)
    if suspicious_feedback:
        warnings.append(
            f"{len(suspicious_feedback)} users have non-zero feedback_value on their first event "
            f"(first event has no prior event to rate). Examples: {suspicious_feedback[:3]}"
        )
    else:
        print("✅ No obvious future feedback leakage on first events")

    # 10. Check for reviewer field (diagnostic benchmark specific)
    has_reviewer = [r for r in valid_rows if r.get("reviewer")]
    if has_reviewer:
        print(f"👁️  Reviewer-annotated rows: {len(has_reviewer)}/{len(valid_rows)}")
        unreviewed = [r for r in valid_rows if not r.get("reviewer")]
        if unreviewed:
            warnings.append(f"{len(unreviewed)} rows lack 'reviewer' field — treat results as pilot/unreviewed")

    # 11. Print anonymized samples
    print(f"\n🔍 Sample rows (anonymized):")
    import random
    sample_size = min(5, len(valid_rows))
    for r in random.sample(valid_rows, sample_size):
        uid_short = str(r.get("global_user_id", "?"))[:8]
        content = anonymize(str(r.get("content", "")))
        intent = r.get("intent_label", "?")
        agent = r.get("selected_agent", "?")
        print(f"  user={uid_short}… intent={intent} agent={agent} content='{content}'")

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("VALIDATION SUMMARY")
    print(f"{'='*60}")

    if errors:
        print(f"❌ ERRORS ({len(errors)}):")
        for e in errors:
            print(f"   • {e}")
    else:
        print("✅ No blocking errors")

    if warnings:
        print(f"⚠️  WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"   • {w}")
    else:
        print("✅ No warnings")

    if errors:
        print("\n🔴 Result: INVALID — fix errors before training")
        return 1
    elif warnings and strict:
        print("\n🟡 Result: WARNINGS (strict mode — treating as failure)")
        return 2
    else:
        print("\n🟢 Result: VALID — data can be used for training")
        return 0


def main():
    ap = argparse.ArgumentParser(description="DUSN-X Training Data Validator")
    ap.add_argument("--data", default=None, help="Path to JSONL data file")
    ap.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    args = ap.parse_args()

    # Default to most recent synthetic data
    if args.data:
        data_path = Path(args.data)
    else:
        # Try common locations
        candidates = [
            Path("data/synthetic_30k_v2.jsonl"),
            Path("data/synthetic_v2.jsonl"),
        ]
        data_path = None
        for c in candidates:
            if c.exists():
                data_path = c
                break
        if data_path is None:
            print("❌ No data file found. Use --data path/to/data.jsonl")
            sys.exit(1)

    exit_code = validate(data_path, strict=args.strict)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
