"""CLI for prediction-blind review exports, validation, agreement reports, CSV conversion, and adjudication."""
import argparse
import csv
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
for path in (REPO_ROOT / "python/src", REPO_ROOT / "python", REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dusnx_core.data_pipeline import read_rows, write_rows
from dusnx_core.review import review_sample, validate_review, agreement, adjudicate


def export_csv(rows, output_path):
    fieldnames = [
        "record_id", "sequence_id", "step", "platform", "session_id", "user_message",
        "reviewer", "review_date", "label_active", "label_obsolete", "label_intent",
        "label_agent", "label_action", "label_requires_clarification", "notes"
    ]
    with open(output_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            labels = r.get("labels", {})
            active = labels.get("active")
            obsolete = labels.get("obsolete")
            writer.writerow({
                "record_id": r.get("record_id"),
                "sequence_id": r.get("sequence_id"),
                "step": r.get("step"),
                "platform": r.get("platform"),
                "session_id": r.get("session_id"),
                "user_message": r.get("user_message"),
                "reviewer": r.get("reviewer") or "",
                "review_date": r.get("review_date") or "",
                "label_active": ", ".join(active) if isinstance(active, list) else (active or ""),
                "label_obsolete": ", ".join(obsolete) if isinstance(obsolete, list) else (obsolete or ""),
                "label_intent": labels.get("intent") or "",
                "label_agent": labels.get("agent") or "",
                "label_action": labels.get("action") or "",
                "label_requires_clarification": labels.get("requires_clarification") if labels.get("requires_clarification") is not None else "",
                "notes": r.get("notes") or "",
            })


def import_csv(input_path):
    rows = []
    with open(input_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            active_raw = r.get("label_active", "").strip()
            obsolete_raw = r.get("label_obsolete", "").strip()
            clarify_raw = r.get("label_requires_clarification", "").strip().lower()
            clarify = True if clarify_raw in ("true", "1", "yes", "có") else (False if clarify_raw in ("false", "0", "no", "không") else None)
            rows.append({
                "record_id": r["record_id"],
                "sequence_id": r["sequence_id"],
                "step": int(r["step"]) if r.get("step") else 1,
                "platform": r.get("platform"),
                "session_id": r.get("session_id"),
                "user_message": r.get("user_message"),
                "reviewer": r.get("reviewer") or None,
                "review_date": r.get("review_date") or None,
                "labels": {
                    "active": [x.strip() for x in active_raw.split(",") if x.strip()] if active_raw else [],
                    "obsolete": [x.strip() for x in obsolete_raw.split(",") if x.strip()] if obsolete_raw else [],
                    "intent": r.get("label_intent") or None,
                    "agent": r.get("label_agent") or None,
                    "action": r.get("label_action") or None,
                    "requires_clarification": clarify,
                },
                "notes": r.get("notes", ""),
            })
    return rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Label review, agreement and adjudication CLI")
    ap.add_argument("--input", required=True, help="Input benchmark/data file or reviewer A file")
    ap.add_argument("--output", required=True, help="Output destination for template, report or adjudication")
    ap.add_argument("--compare-with", help="Path to reviewer B file for agreement comparison")
    ap.add_argument("--sequences", type=int, default=None, help="Number of sequences to sample (default all)")
    ap.add_argument("--seed", type=int, default=42, help="Random seed for sampling")
    ap.add_argument("--validate", action="store_true", help="Validate reviewer formatting")
    ap.add_argument("--to-csv", action="store_true", help="Convert JSONL review template to CSV for Excel/Sheets")
    ap.add_argument("--from-csv", action="store_true", help="Convert completed CSV review back to JSONL")
    ap.add_argument("--adjudicate", action="store_true", help="Produce adjudication file from two reviews")
    ap.add_argument("--adjudicator", help="Name of independent adjudicator")
    args = ap.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.to_csv:
        rows = read_rows(input_path)
        export_csv(rows, output_path)
        print(f"Exported CSV review sheet with {len(rows)} rows to {output_path}")
    elif args.from_csv:
        rows = import_csv(input_path)
        write_rows(output_path, rows)
        print(f"Converted CSV review to JSONL with {len(rows)} records at {output_path}")
    elif args.validate:
        rows = import_csv(input_path) if str(input_path).endswith(".csv") else read_rows(input_path)
        count = validate_review(rows)
        print(f"Valid review file: {count} records reviewed in {input_path}")
    elif args.compare_with and not args.adjudicate:
        left = import_csv(input_path) if str(input_path).endswith(".csv") else read_rows(input_path)
        right = import_csv(args.compare_with) if str(args.compare_with).endswith(".csv") else read_rows(args.compare_with)
        rep = agreement(left, right)
        output_path.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Agreement calculated for {rep['records']} records. Disagreements: {len(rep['disagreements'])}. Written to {output_path}")
    elif args.adjudicate:
        if not args.compare_with:
            raise ValueError("--compare-with is required for adjudication")
        if not args.adjudicator:
            raise ValueError("--adjudicator name is required for adjudication")
        left = import_csv(input_path) if str(input_path).endswith(".csv") else read_rows(input_path)
        right = import_csv(args.compare_with) if str(args.compare_with).endswith(".csv") else read_rows(args.compare_with)
        adj = adjudicate(left, right, adjudicator=args.adjudicator)
        output_path.write_text(json.dumps(adj, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Adjudication record written to {output_path}. Status: {adj['status']}. Total records: {adj['total_records']}")
    else:
        # Default: export blind review template
        rows = read_rows(input_path)
        template = review_sample(rows, seed=args.seed, sequences=args.sequences)
        write_rows(output_path, template)
        print(f"Exported {len(template)} blind review items from {input_path} to {output_path}")
