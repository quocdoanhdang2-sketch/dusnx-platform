"""Prediction-blind review exports and agreement reports. Never self-approve."""
from collections import defaultdict
import random
from sklearn.metrics import cohen_kappa_score

FIELDS=("active","obsolete","intent","agent","action","requires_clarification")


def review_sample(rows,seed=42,sequences=10):
    groups=defaultdict(list)
    for r in rows:groups[r["sequence_id"]].append(r)
    chosen=random.Random(seed).sample(sorted(groups),min(sequences,len(groups)))
    result=[]
    for seq in chosen:
        for i,r in enumerate(groups[seq],1):
            result.append(dict(record_id=r.get("case_id",r.get("event_id")),sequence_id=seq,step=r.get("step",i),
                user_message=r.get("user_message",r.get("content")),platform=r["platform"],
                session_id=r.get("session_id"),source=r.get("source"),reviewer=None,
                labels={key:None for key in FIELDS},notes=""))
    return result


def agreement(left,right):
    def index(rows):
        result={}
        for r in rows:
            if not r.get("reviewer") or any(r["labels"].get(k) is None for k in FIELDS):raise ValueError("incomplete review")
            if r["record_id"] in result:raise ValueError("duplicate review record")
            result[r["record_id"]]=r
        return result
    a,b=index(left),index(right)
    if set(a)!=set(b):raise ValueError("review sets differ")
    if {r["reviewer"] for r in a.values()} & {r["reviewer"] for r in b.values()}:raise ValueError("distinct reviewers required")
    result={"records":len(a),"fields":{},"disagreements":[]}
    for key in FIELDS:
        def label(r):
            v=r["labels"][key]
            return str(sorted(v) if isinstance(v,list) else v)
        x=[label(a[k]) for k in sorted(a)];y=[label(b[k]) for k in sorted(a)]
        diff=[k for k in sorted(a) if label(a[k])!=label(b[k])]
        result["fields"][key]={"agreement":1-len(diff)/len(a) if a else None,
            "kappa":float(cohen_kappa_score(x,y)) if len(set(x+y))>1 else None}
        result["disagreements"] += [dict(record_id=k,field=key,left=a[k]["labels"][key],right=b[k]["labels"][key]) for k in diff]
    return result
