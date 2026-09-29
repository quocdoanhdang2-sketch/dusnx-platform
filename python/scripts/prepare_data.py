"""Prepare bounded, provenance-preserving training partitions; never read predictions."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
for path in (REPO_ROOT / "python/src", REPO_ROOT / "python", REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dusnx_core.data_pipeline import read_rows, write_rows, statistics, validate_training, assert_disjoint, sha256, norm
from dusnx_core.designed_data import generate_designed


def prepare(output, legacy=None, external=None, seed=20260929, legacy_sequences=100):
    output=Path(output); output.mkdir(parents=True,exist_ok=True)
    parts=generate_designed(seed)
    report={"seed":seed,"external_unlabelled_excluded":0,"legacy_limit_reason":"Repeated synthetic templates: cap at 100 complete sequences; do not inflate by renaming."}
    if legacy:
        rows=read_rows(legacy);report["legacy_available"]=statistics(rows);report["legacy_sha256"]=sha256(legacy)
        grouped=defaultdict(list)
        for row in rows:grouped[row["global_user_id"]].append(row)
        for uid in sorted(grouped)[:min(legacy_sequences,100)]:
            for i,row in enumerate(sorted(grouped[uid],key=lambda r:r["event_time_utc"])):
                row=dict(row,event_id=f"legacy-{uid}-{i}",sequence_id=f"legacy-{uid}",source="legacy_synthetic",
                         template_family="legacy_generator",layout="multi_turn",partition="train",
                         label_provenance="legacy_synthetic_not_independently_reviewed")
                parts["train"].append(row)
    if external:
        for row in read_rows(external):
            if row.get("intent_label") is not None and row.get("label_provenance")=="reviewed_mapping":
                parts["train"].append(dict(row,partition="train"))
            else:report["external_unlabelled_excluded"]+=1
    # Keep whole sequences; deduplicate repeated trajectories, not isolated confirmations.
    seen=set();report["duplicate_sequences_removed"]=0
    for split,rows in parts.items():
        groups=defaultdict(list)
        for row in rows:groups[row["sequence_id"]].append(row)
        cleaned=[]
        for sequence in groups.values():
            signature=tuple(norm(r["content"]) for r in sequence)
            if signature in seen:report["duplicate_sequences_removed"]+=1;continue
            seen.add(signature);cleaned.extend(sequence)
        parts[split]=cleaned
        report[split]=validate_training(cleaned)
    assert_disjoint(parts)
    # Audit identities/whole conversations only; gold labels never enter training.
    exclusions={}
    for filename in ("benchmarks/week3_personalization_pilot.jsonl","benchmarks/holdout_v1.jsonl"):
        if Path(filename).exists():
            exclusions[filename]=[dict(global_user_id=r.get("global_user_id") or "benchmark-"+r["sequence_id"],
                sequence_id=r["sequence_id"],template_family=r.get("template_family") or "benchmark-"+r["sequence_id"],
                user_message=r["user_message"]) for r in read_rows(filename)]
    assert_disjoint({**parts,**exclusions})
    report["benchmark_exclusions"]={name:sha256(name) for name in exclusions}
    for split,rows in parts.items():
        path=output/f"{split}.jsonl";write_rows(path,rows);report[split]["sha256"]=sha256(path)
    (output/"manifest.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    return report


if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--output",default="runtime/prepared")
    ap.add_argument("--legacy");ap.add_argument("--external");ap.add_argument("--seed",type=int,default=20260929)
    args=ap.parse_args();print(json.dumps(prepare(args.output,args.legacy,args.external,args.seed),ensure_ascii=False,indent=2))
