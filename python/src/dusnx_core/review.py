"""Prediction-blind review exports, gold normalization, validation, agreement reports, and adjudication.

Never self-approve or claim AI-generated labels are human-reviewed.
"""
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import random
from typing import Any, Optional
from sklearn.metrics import cohen_kappa_score

FIELDS = ("active", "obsolete", "intent", "agent", "action", "requires_clarification")
CATEGORICAL_FIELDS = ("intent", "agent", "action", "requires_clarification")
SET_FIELDS = ("active", "obsolete")

ALLOWED_INTENTS = {
    "chat", "research", "summarize", "presentation_edit", "recommendation", "followup",
    "memory_create", "decision_modify_intent", "decision_update", "decision_update_cancelled",
    "clarify_missing_context", "clarify_ambiguous_decision",
}
ALLOWED_AGENTS = {"conversation", "search_rag", "productivity", "memory"}
ALLOWED_ACTIONS = {
    "reply", "search", "summarize", "edit_slide", "recommend", "clarify",
    "create_memory", "update_memory", "await_confirm", "no_op",
}


def review_sample(rows, seed=42, sequences=None):
    """Generate a blind review file where predictions/gold answers are strictly stripped.

    Verified to contain NO expected_*, gold_*, keywords, or non-null labels.
    """
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


def normalize_gold_benchmark(rows, reviewer_tag="gold_ground_truth"):
    """Convert raw locked benchmark rows into the standard review schema for fair comparison."""
    result = []
    for i, r in enumerate(rows, 1):
        rid = r.get("case_id", r.get("event_id", f"gold_step_{i}"))
        active = r.get("gold_active_facts", [])
        obsolete = r.get("gold_obsolete_facts", [])
        if isinstance(active, str):
            active = [a.strip() for a in active.split(",") if a.strip()]
        if isinstance(obsolete, str):
            obsolete = [o.strip() for o in obsolete.split(",") if o.strip()]
        result.append({
            "record_id": rid,
            "sequence_id": r.get("sequence_id", "seq_unknown"),
            "step": r.get("step", i),
            "user_message": r.get("user_message", r.get("content", "")),
            "platform": r.get("platform", "web"),
            "session_id": r.get("session_id"),
            "source": r.get("source", "benchmark_gold"),
            "reviewer": reviewer_tag,
            "review_date": "locked_benchmark",
            "labels": {
                "active": sorted(list(set(active))),
                "obsolete": sorted(list(set(obsolete))),
                "intent": r.get("expected_intent"),
                "agent": r.get("expected_agent"),
                "action": r.get("expected_next_action"),
                "requires_clarification": bool(r.get("requires_clarification", False)),
            },
            "notes": "official_gold_benchmark_reference",
        })
    return result


def is_blind_template(rows) -> bool:
    """True if all rows have empty reviewers and unlabelled fields."""
    if not rows:
        return False
    for r in rows:
        if r.get("reviewer") and str(r.get("reviewer")).strip():
            return False
        labels = r.get("labels", {})
        for k in ("intent", "agent", "action", "requires_clarification"):
            if labels.get(k) is not None:
                return False
        for k in ("active", "obsolete"):
            val = labels.get(k)
            if val and len(val) > 0:
                return False
    return True


def validate_review(rows, allow_partial=False):
    """Validate review formatting, schema, and non-emptiness before agreement check."""
    if not rows:
        raise ValueError("Review dataset is empty")
    if is_blind_template(rows):
        raise ValueError("File is an unlabelled blind review template. It cannot be used as a reviewer submission or gold reference.")
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
        review_date=r.get("review_date")
        if review_date and review_date != "locked_benchmark":
            try:
                datetime.fromisoformat(review_date.replace("Z", "+00:00"))
            except (ValueError,TypeError) as exc:
                raise ValueError(f"Row {idx} ({rid}): invalid review_date") from exc
        labels = r.get("labels", {})
        for f in FIELDS:
            val = labels.get(f)
            if val is None and not allow_partial:
                raise ValueError(f"Row {idx} ({rid}): field '{f}' is not labeled")
            if val is not None:
                if f == "intent" and val not in ALLOWED_INTENTS:
                    raise ValueError(f"Row {idx} ({rid}): invalid intent '{val}'. Allowed: {sorted(ALLOWED_INTENTS)}")
                if f == "agent" and val not in ALLOWED_AGENTS:
                    raise ValueError(f"Row {idx} ({rid}): invalid agent '{val}'. Allowed: {sorted(ALLOWED_AGENTS)}")
                if f == "action" and val not in ALLOWED_ACTIONS:
                    raise ValueError(f"Row {idx} ({rid}): invalid action '{val}'. Allowed: {sorted(ALLOWED_ACTIONS)}")
                if f == "requires_clarification" and not isinstance(val, bool):
                    raise ValueError(f"Row {idx} ({rid}): requires_clarification must be boolean, got {type(val).__name__}")
                if f in ("active", "obsolete") and not isinstance(val, (list, set, tuple)):
                    raise ValueError(f"Row {idx} ({rid}): {f} must be a list/set of facts, got {type(val).__name__}")
                if f in ("active", "obsolete") and isinstance(val,(list,set,tuple)) and not all(isinstance(x,str) and x.strip() for x in val):
                    raise ValueError(f"Row {idx} ({rid}): {f} must contain nonempty strings")
    return len(rows)


def validate_submission(rows, template):
    """Validate a real submission against a blind reference, never against gold."""
    if any(any(k.startswith(("gold_","expected_")) for k in r) for r in rows):
        raise ValueError("Gold benchmark is not a reviewer submission")
    validate_review(rows)
    if not is_blind_template(template):raise ValueError("Reference must be an unfilled blind template")
    if [r["record_id"] for r in rows] != [r["record_id"] for r in template]:
        raise ValueError("Submission must contain every reference row in the same order")
    for row,original in zip(rows,template):
        for key in ("record_id","sequence_id","step","platform","session_id","user_message"):
            if row.get(key)!=original.get(key):raise ValueError(f"Changed reference field {key}: {row['record_id']}")
        if not row.get("review_date") or row["review_date"]=="locked_benchmark":raise ValueError("Human review_date required")
        if str(row["reviewer"]).startswith("gold_"):raise ValueError("Gold is not a human reviewer")
    return len(rows)


def agreement(left, right):
    """Compute agreement and Cohen's kappa between two reviewed datasets (or reviewer vs gold)."""
    if is_blind_template(left) or is_blind_template(right):
        raise ValueError("Cannot compute agreement against an unlabelled blind template.")

    def index(rows):
        result = {}
        for r in rows:
            if not r.get("reviewer"):
                raise ValueError(f"Record {r.get('record_id')} has no reviewer identity")
            labels = r.get("labels", {})
            if any(labels.get(k) is None for k in FIELDS):
                raise ValueError(f"Incomplete review in record {r.get('record_id')}")
            if r["record_id"] in result:
                raise ValueError(f"Duplicate review record {r['record_id']}")
            result[r["record_id"]] = r
        return result

    a, b = index(left), index(right)
    if set(a) != set(b):
        raise ValueError(f"Review sets record IDs differ: {len(a)} vs {len(b)}")
    if {r["reviewer"] for r in a.values()} & {r["reviewer"] for r in b.values()}:
        raise ValueError("distinct reviewers required; cannot compare reviewer with themselves")

    result = {
        "records": len(a),
        "reviewers": [
            sorted(list({r["reviewer"] for r in a.values()}))[0],
            sorted(list({r["reviewer"] for r in b.values()}))[0],
        ],
        "fields": {},
        "disagreements": [],
    }

    for key in FIELDS:
        def label_repr(r):
            v = r["labels"][key]
            if isinstance(v, (list, set, tuple)):
                return str(sorted([str(x).strip().lower() for x in v]))
            return str(v).strip().lower()

        x = [label_repr(a[k]) for k in sorted(a)]
        y = [label_repr(b[k]) for k in sorted(a)]
        diff = [k for k in sorted(a) if label_repr(a[k]) != label_repr(b[k])]

        # Cohen's kappa is appropriate for discrete categorical variables
        kappa_val = None
        if key in CATEGORICAL_FIELDS:
            distinct_classes = sorted(list(set(x + y)))
            if len(distinct_classes) > 1:
                try:
                    kappa_val = float(cohen_kappa_score(x, y, labels=distinct_classes))
                except Exception:
                    kappa_val = None

        result["fields"][key] = {
            "agreement_rate": round(1.0 - (len(diff) / len(a)), 4) if a else None,
            "disagreements_count": len(diff),
            "cohen_kappa": round(kappa_val, 4) if kappa_val is not None else None,
        }
        result["disagreements"] += [
            dict(
                record_id=k,
                field=key,
                left_reviewer=a[k]["reviewer"],
                left_value=a[k]["labels"][key],
                right_reviewer=b[k]["reviewer"],
                right_value=b[k]["labels"][key],
            )
            for k in diff
        ]
    return result


def adjudicate(left, right, adjudicator, resolved_labels=None, status=None, notes=""):
    """Produce an adjudication audit trail from two reviews or reviewer vs gold.

    Does NOT fabricate human approval; preserves full disagreement history and distinct adjudicator.
    """
    if not adjudicator or not adjudicator.strip():
        raise ValueError("Adjudicator name must be provided")

    rep = agreement(left, right)
    a = {r["record_id"]: r for r in left}
    b = {r["record_id"]: r for r in right}

    # Determine honest status
    if status is None:
        is_test = "test" in adjudicator.lower() or "mock" in adjudicator.lower() or "fake" in adjudicator.lower()
        status = "test_only_synthetic_adjudication" if is_test else "draft_pending_human_attestation"

    resolved_labels = resolved_labels or {}

    adjudication = {
        "adjudicator": adjudicator,
        "adjudicated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "reviewers": sorted(list({r["reviewer"] for r in left} | {r["reviewer"] for r in right})),
        "total_records": rep["records"],
        "fields_agreement": rep["fields"],
        "disagreements_count": len(rep["disagreements"]),
        "notes": notes,
        "records": [],
    }

    for r in left:
        rid = r["record_id"]
        rec_disagreements = [d for d in rep["disagreements"] if d["record_id"] == rid]
        labels = {}
        resolutions = {}
        for f in FIELDS:
            dis = [d for d in rec_disagreements if d["field"] == f]
            if not dis:
                labels[f] = a[rid]["labels"][f]
            else:
                if rid in resolved_labels and f in resolved_labels[rid]:
                    res = resolved_labels[rid][f]
                    labels[f] = res.get("resolved_value", res) if isinstance(res, dict) else res
                    resolutions[f] = res.get("reason", "Resolved during adjudication") if isinstance(res, dict) else "Manual resolution"
                else:
                    labels[f] = "PENDING_HUMAN_RESOLUTION"
                    resolutions[f] = "Unresolved disagreement between annotators"

        adjudication["records"].append({
            "record_id": rid,
            "sequence_id": a[rid]["sequence_id"],
            "step": a[rid]["step"],
            "user_message": a[rid]["user_message"],
            "labels": labels,
            "resolutions": resolutions if resolutions else None,
            "disagreements": rec_disagreements if rec_disagreements else None,
        })
    return adjudication
