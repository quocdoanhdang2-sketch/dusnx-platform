"""CLI for prediction-blind review exports, validation, gold comparison, agreement reports, CSV conversion, and adjudication."""
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
from dusnx_core.review import (
    review_sample, validate_review, agreement, adjudicate,
    normalize_gold_benchmark, is_blind_template, FIELDS, validate_submission
)


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
            clarify = labels.get("requires_clarification")
            clarify_str = "true" if clarify is True else ("false" if clarify is False else "")
            writer.writerow({
                "record_id": r.get("record_id"),
                "sequence_id": r.get("sequence_id"),
                "step": r.get("step"),
                "platform": r.get("platform"),
                "session_id": r.get("session_id"),
                "user_message": r.get("user_message"),
                "reviewer": r.get("reviewer") or "",
                "review_date": r.get("review_date") or "",
                "label_active": json.dumps(list(active),ensure_ascii=False) if isinstance(active, (list, set, tuple)) else (active or ""),
                "label_obsolete": json.dumps(list(obsolete),ensure_ascii=False) if isinstance(obsolete, (list, set, tuple)) else (obsolete or ""),
                "label_intent": labels.get("intent") or "",
                "label_agent": labels.get("agent") or "",
                "label_action": labels.get("action") or "",
                "label_requires_clarification": clarify_str,
                "notes": r.get("notes") or "",
            })


def import_csv(input_path):
    def facts(value):
        if not value:return None  # blank means not reviewed; explicit [] means no facts.
        if value.startswith("["):
            parsed=json.loads(value)
            if not isinstance(parsed,list) or not all(isinstance(x,str) for x in parsed):raise ValueError("Fact field must be a JSON string array")
            return parsed
        return [x.strip() for x in value.split(",") if x.strip()]
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
                    "active": facts(active_raw),
                    "obsolete": facts(obsolete_raw),
                    "intent": r.get("label_intent") or None,
                    "agent": r.get("label_agent") or None,
                    "action": r.get("label_action") or None,
                    "requires_clarification": clarify,
                },
                "notes": r.get("notes", ""),
            })
    return rows


def load_reviewed_records(path: Path, *, allow_gold=False):
    if str(path).endswith(".csv"):
        return import_csv(path)
    raw = read_rows(path)
    # Check if this is a gold benchmark file with expected_* fields rather than labels
    if raw and ("expected_intent" in raw[0] or "expected_agent" in raw[0]):
        if not allow_gold:raise ValueError("Gold benchmark is not a reviewer submission; use explicit --gold only for comparison")
        return normalize_gold_benchmark(raw)
    return raw


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Label review, agreement, gold comparison, and adjudication CLI")
    ap.add_argument("--input", required=True, help="Input benchmark/data file or reviewer A file")
    ap.add_argument("--output", help="Output destination for template, report, or adjudication")
    ap.add_argument("--compare-with", help="Path to reviewer B file for agreement comparison")
    ap.add_argument("--gold", help="Path to private gold benchmark file to compare reviewer against")
    ap.add_argument("--sequences", type=int, default=None, help="Number of sequences to sample (default all)")
    ap.add_argument("--seed", type=int, default=42, help="Random seed for sampling")
    ap.add_argument("--validate", action="store_true", help="Validate reviewer formatting and schema")
    ap.add_argument("--template", help="Blind reference: validate every row and immutable input fields")
    ap.add_argument("--to-csv", action="store_true", help="Convert JSONL review template to CSV for Excel/Sheets")
    ap.add_argument("--from-csv", action="store_true", help="Convert completed CSV review back to JSONL")
    ap.add_argument("--adjudicate", action="store_true", help="Produce adjudication file from two reviews or reviewer vs gold")
    ap.add_argument("--adjudicator", help="Name of independent adjudicator")
    ap.add_argument("--resolutions", help="Optional JSON file with resolved labels for disagreements")
    ap.add_argument("--blind", action="store_true", help="Export an unlabelled blind review package")
    args = ap.parse_args()

    input_path = Path(args.input)
    if not args.validate and not args.output:
        raise ValueError("--output is required for this action")
    output_path = Path(args.output) if args.output else None
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.to_csv:
        rows = load_reviewed_records(input_path)
        export_csv(rows, output_path)
        print(f"Exported CSV review sheet with {len(rows)} rows to {output_path}")
    elif args.from_csv:
        rows = import_csv(input_path)
        write_rows(output_path, rows)
        print(f"Converted CSV review to JSONL with {len(rows)} records at {output_path}")
    elif args.validate:
        rows = load_reviewed_records(input_path)
        count = validate_submission(rows,load_reviewed_records(Path(args.template))) if args.template else validate_review(rows)
        print(f"Valid review file: {count} records verified in {input_path}")
    elif args.adjudicate:
        if not args.adjudicator:
            raise ValueError("--adjudicator name is required for adjudication")
        target_second = Path(args.gold) if args.gold else (Path(args.compare_with) if args.compare_with else None)
        if not target_second:
            raise ValueError("Either --gold or --compare-with is required for adjudication")
        left = load_reviewed_records(input_path)
        right = load_reviewed_records(target_second,allow_gold=bool(args.gold))
        if is_blind_template(left) or is_blind_template(right):
            raise ValueError("Cannot adjudicate an unlabelled blind template.")
        resolutions = json.loads(Path(args.resolutions).read_text(encoding="utf-8")) if args.resolutions else None
        adj = adjudicate(left, right, adjudicator=args.adjudicator, resolved_labels=resolutions)
        output_path.write_text(json.dumps(adj, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Adjudication record written to {output_path}. Status: {adj['status']}. Total records: {adj['total_records']}, Disagreements: {adj['disagreements_count']}")
    elif args.gold or args.compare_with:
        reviewer_file = input_path
        if args.gold:
            gold_rows = load_reviewed_records(Path(args.gold),allow_gold=True)
            rev_rows = load_reviewed_records(reviewer_file)
            if is_blind_template(rev_rows):
                raise ValueError("The reviewer file is an unfilled blind template! Cannot compare unlabelled data against gold.")
            rep = agreement(rev_rows, gold_rows)
            print(f"Comparison with gold benchmark ({Path(args.gold).name}): {rep['records']} records. Disagreements: {len(rep['disagreements'])}.")
        else:
            left = load_reviewed_records(input_path)
            right = load_reviewed_records(Path(args.compare_with))
            if is_blind_template(left) or is_blind_template(right):
                raise ValueError("Cannot compare against an unlabelled blind template. Both files must have completed labels.")
            rep = agreement(left, right)
            print(f"Inter-reviewer agreement: {rep['records']} records. Disagreements: {len(rep['disagreements'])}.")
        output_path.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Agreement report written to {output_path}")
    else:
        # Default: export blind review template
        rows = read_rows(input_path)
        template = review_sample(rows, seed=args.seed, sequences=args.sequences)
        write_rows(output_path, template)
        print(f"Exported {len(template)} blind review items from {input_path} to {output_path}")
