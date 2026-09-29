"""Integrity/blankness checks only. Never parse holdout labels or run inference."""
import argparse
import csv
import hashlib
import json
from pathlib import Path


FIELDS={"active","obsolete","intent","agent","action","requires_clarification"}
INPUTS=("record_id","sequence_id","step","platform","session_id","user_message")


def audit(benchmark,manifest,blind_jsonl,blind_csv):
    manifest=json.loads(Path(manifest).read_text(encoding="utf-8"))
    # Only opaque bytes of the gold file are accessed here.
    digest=hashlib.sha256(Path(benchmark).read_bytes()).hexdigest()
    if digest!=manifest["sha256"]:raise ValueError("Holdout hash mismatch")
    rows=[json.loads(line) for line in Path(blind_jsonl).read_text(encoding="utf-8").splitlines() if line]
    allowed=set(INPUTS)|{"source","reviewer","review_date","labels","notes"}
    for row in rows:
        if set(row)-allowed or row.get("notes") or row.get("reviewer") or row.get("review_date"):
            raise ValueError("Unexpected field or nonblank reviewer annotation in blind package")
        if set(row.get("labels",{}))!=FIELDS or any(v is not None for v in row["labels"].values()):
            raise ValueError("Blind JSONL contains labels")
    with Path(blind_csv).open(encoding="utf-8-sig",newline="") as fh:
        reader=csv.DictReader(fh);csv_rows=list(reader)
        expected=set(INPUTS)|{"reviewer","review_date","notes"}|{"label_"+f for f in FIELDS}
        if set(reader.fieldnames or [])!=expected:raise ValueError("Unexpected CSV columns")
    if len(rows)!=manifest["events"] or len(csv_rows)!=len(rows):raise ValueError("Missing blind rows")
    if len({r["record_id"] for r in rows})!=len(rows):raise ValueError("Duplicate blind IDs")
    if len({r["sequence_id"] for r in rows})!=len(manifest["sequence_ids"]):raise ValueError("Sequence count mismatch")
    for a,b in zip(rows,csv_rows):
        if any(str(a.get(k) or "")!=b[k] for k in INPUTS):raise ValueError("CSV/JSONL inputs differ")
        if any(b[k] for k in expected-set(INPUTS)):raise ValueError("Blind CSV contains annotations")
    return dict(status="integrity_and_blankness_verified",sha256=digest,events=len(rows),
                sequences=len({r["sequence_id"] for r in rows}),review_status=manifest["status"],
                inference_run=False,gold_labels_parsed=False,
                blind_sha256={Path(p).name:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in (blind_jsonl,blind_csv)})


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--benchmark",required=True);p.add_argument("--manifest",required=True)
    p.add_argument("--jsonl",required=True);p.add_argument("--csv",required=True);p.add_argument("--output")
    a=p.parse_args();report=audit(a.benchmark,a.manifest,a.jsonl,a.csv)
    if a.output:Path(a.output).write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))
