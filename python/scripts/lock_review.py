"""Freeze a separately reviewed label artifact only after explicit human attestation.

Does not edit the original benchmark, run evaluation, or infer human approval.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
from review_labels import load_reviewed_records
from dusnx_core.review import validate_submission,validate_review,agreement


def freeze(adjudication,review_a,review_b,template,output,*,attest=False,gold_reference=False):
    if not attest:raise ValueError("Explicit --attest-human-review required after real human review")
    paths=[Path(p) for p in (adjudication,review_a,review_b,template)]
    a=load_reviewed_records(paths[1]);b=load_reviewed_records(paths[2],allow_gold=gold_reference)
    blind=load_reviewed_records(paths[3])
    validate_submission(a,blind)
    if not gold_reference:validate_submission(b,blind)
    agreement(a,b)
    adj=json.loads(paths[0].read_text(encoding="utf-8"))
    if not adj.get("adjudicator") or adj.get("status")!="draft_pending_human_attestation":
        raise ValueError("Only a complete human adjudication draft may be attested")
    if [r["record_id"] for r in adj["records"]]!=[r["record_id"] for r in blind]:raise ValueError("Adjudication IDs differ")
    if sorted(adj["reviewers"])!=sorted({r["reviewer"] for r in a+b}):raise ValueError("Adjudication reviewer identities differ")
    now=datetime.now(timezone.utc).isoformat()
    final=[]
    for source,resolved in zip(blind,adj["records"]):
        if resolved["user_message"]!=source["user_message"]:raise ValueError("Adjudication changed input")
        if any(v=="PENDING_HUMAN_RESOLUTION" for v in resolved["labels"].values()):raise ValueError("Unresolved disagreement")
        final.append(dict(source,labels=resolved["labels"],reviewer=adj["adjudicator"],review_date=now))
    validate_review(final)
    out=Path(output);manifest=out.with_suffix(".manifest.json")
    if out.exists() or manifest.exists():raise ValueError("Review lock already exists; use a new version")
    out.parent.mkdir(parents=True,exist_ok=True)
    payload="".join(json.dumps(r,ensure_ascii=False)+"\n" for r in final)
    meta=dict(status="operator_attested_human_review",attested_by=adj["adjudicator"],timestamp_utc=now,
        records=len(final),sha256=hashlib.sha256(payload.encode()).hexdigest(),
        source_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        original_benchmark_modified=False,evaluation_run=False,gold_reference=gold_reference)
    with out.open("x",encoding="utf-8",newline="\n") as fh:fh.write(payload)
    with manifest.open("x",encoding="utf-8",newline="\n") as fh:json.dump(meta,fh,ensure_ascii=False,indent=2)
    return meta


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--adjudication",required=True);p.add_argument("--reviewer-a",required=True)
    p.add_argument("--reviewer-b",required=True);p.add_argument("--template",required=True);p.add_argument("--output",required=True)
    p.add_argument("--attest-human-review",action="store_true");p.add_argument("--gold-reference",action="store_true");a=p.parse_args()
    print(json.dumps(freeze(a.adjudication,a.reviewer_a,a.reviewer_b,a.template,a.output,
                          attest=a.attest_human_review,gold_reference=a.gold_reference),indent=2))
