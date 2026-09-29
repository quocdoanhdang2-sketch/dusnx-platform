"""Prediction-blind review exports and agreement reports. Never self-approve."""
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import random
from sklearn.metrics import cohen_kappa_score

FIELDS = ("active", "obsolete", "intent", "agent", "action", "requires_clarification")
ALLOWED_INTENTS = {"chat", "research", "summarize", "presentation_edit", "recommendation", "followup",
                   "memory_create", "decision_modify_intent", "decision_update", "decision_update_cancelled",
                   "clarify_missing_context", "clarify_ambiguous_decision"}
ALLOWED_AGENTS = {"conversation", "search_rag", "productivity", "memory"}
ALLOWED_ACTIONS = {"reply", "search", "summarize", "edit_slide", "recommend", "clarify",
                   "create_memory", "update_memory", "await_confirm", "no_op"}


def review_sample(rows, seed=42, sequences=None):
    """Generate a blind review file where predictions/gold answers are hidden."""
    groups = defaultdict(list)
    for r in rows:
        groups[r["sequence_id"]].append(r)
    chosen = sorted(groups) if sequences is None else random.Random(seed).sample(sorted(groups), min(sequences, len(groups)))
    result = []
    for seq in chosen:
        for i, r in enumerate(groups[seq], 1):
            result.append(dict(
                record_id=r.get("case_id", r.get("event_id")),
                sequence_id=seq,
                step=r.get("step", i),
                user_message=r.get("user_message", r.get("content")),
                platform=r["platform"],
                session_id=r.get("session_id"),
                source=r.get("source"),
                reviewer=None,
                review_date=None,
                labels={key: None for key in FIELDS},
                notes="",
            ))
    return result


def validate_review(rows):
    """Validate review formatting and non-emptiness before agreement check."""
    if not rows:
        raise ValueError("Review dataset is empty")
    seen = set()
    for idx, r in enumerate(rows):
        rid = r.get("record_id")
        if not rid:
            raise ValueError(f"Row {idx}: missing record_id")
        if rid in seen:
            raise ValueError(f"Duplicate record_id: {rid}")
        seen.add(rid)
        if not r.get("reviewer") or not str(r["reviewer"]).strip():
            raise ValueError(f"Row {idx} ({rid}): reviewer name cannot be empty")
        labels = r.get("labels", {})
        for f in FIELDS:
            if labels.get(f) is None:
                raise ValueError(f"Row {idx} ({rid}): field '{f}' is not labeled")
    return len(rows)


def agreement(left, right):
    def index(rows):
        result = {}
        for r in rows:
            if not r.get("reviewer") or any(r["labels"].get(k) is None for k in FIELDS):
                raise ValueError("incomplete review")
            if r["record_id"] in result:
                raise ValueError("duplicate review record")
            result[r["record_id"]] = r
        return result

    a, b = index(left), index(right)
    if set(a) != set(b):
        raise ValueError(f"review sets differ: {len(a)} vs {len(b)}")
    if {r["reviewer"] for r in a.values()} & {r["reviewer"] for r in b.values()}:
        raise ValueError("distinct reviewers required; cannot compare reviewer with themselves")
    result = {"records": len(a), "fields": {}, "disagreements": []}
    for key in FIELDS:
        def label(r):
            v = r["labels"][key]
            return str(sorted(v) if isinstance(v, list) else v)

        x = [label(a[k]) for k in sorted(a)]
        y = [label(b[k]) for k in sorted(a)]
        diff = [k for k in sorted(a) if label(a[k]) != label(b[k])]
        result["fields"][key] = {
            "agreement": 1 - len(diff) / len(a) if a else None,
            "kappa": float(cohen_kappa_score(x, y)) if len(set(x + y)) > 1 else None,
        }
        result["disagreements"] += [
            dict(record_id=k, field=key, left=a[k]["labels"][key], right=b[k]["labels"][key])
            for k in diff
        ]
    return result


def adjudicate(left, right, adjudicator, resolved_labels=None, status="adjudicated_pending_final_signoff"):
    """Produce an adjudication report from two distinct reviews.

    Does NOT fabricate human approval; preserves full disagreement history and distinct adjudicator.
    """
    if not adjudicator or not adjudicator.strip():
        raise ValueError("Adjudicator name must be provided")
    rep = agreement(left, right)
    a = {r["record_id"]: r for r in left}
    b = {r["record_id"]: r for r in right}
    adjudication = {
        "adjudicator": adjudicator,
        "adjudicated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "reviewers": sorted(list({r["reviewer"] for r in left} | {r["reviewer"] for r in right})),
        "total_records": rep["records"],
        "fields_agreement": rep["fields"],
        "disagreements_count": len(rep["disagreements"]),
        "records": [],
    }
    for rid in sorted(a):
        rec_disagreements = [d for d in rep["disagreements"] if d["record_id"] == rid]
        labels = {}
        for f in FIELDS:
            dis = [d for d in rec_disagreements if d["field"] == f]
            if not dis:
                labels[f] = a[rid]["labels"][f]
            else:
                labels[f] = (resolved_labels or {}).get(rid, {}).get(f, "PENDING_RESOLUTION")
        adjudication["records"].append({
            "record_id": rid,
            "sequence_id": a[rid]["sequence_id"],
            "step": a[rid]["step"],
            "user_message": a[rid]["user_message"],
            "labels": labels,
            "disagreements": rec_disagreements,
        })
    return adjudication
