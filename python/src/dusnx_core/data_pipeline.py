"""Provenance-preserving import, review and split validation for router training."""
from __future__ import annotations
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import re
import unicodedata

from .constants import INTENTS, AGENTS, NEXT_ACTIONS, PLATFORMS


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def write_rows(path, rows):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text("".join(json.dumps(r,ensure_ascii=False,sort_keys=True)+"\n" for r in rows),encoding="utf-8",newline="\n")


def norm(text):
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


PII_PATTERNS = {
    "email": r"\b[^\s@]+@[^\s@]+\.[^\s@]+",
    "phone_or_identifier": r"(?<!\w)(?:\+?\d[ .()-]?){9,}(?!\w)",
    "secret": r"(?i)\b(?:bearer\s+\S+|sk-[a-z0-9]{12,}|gh[pous]_[a-z0-9]{12,})",
    "address": r"(?i)\b(?:địa chỉ|số nhà|cccd|cmnd|hộ chiếu|tài khoản ngân hàng)\b",
    "personal_name_cue": r"(?i)\b(?:tôi tên là|họ và tên|tên khách hàng)\b",
    "redacted_pii": r"(?i)<(?:số điện thoại|phone|email|address|tên|name)[^>]*>",
}


def pii_reasons(text):
    return [key for key, pattern in PII_PATTERNS.items() if re.search(pattern,unicodedata.normalize("NFC",text))]


def redact(text):
    text=unicodedata.normalize("NFC",text)
    for key, pattern in PII_PATTERNS.items():
        text=re.sub(pattern, f"[REDACTED:{key}]", text)
    return text


def statistics(rows):
    texts=[norm(r.get("content",r.get("user_message",""))) for r in rows]
    return {
        "events": len(rows), "sequences":len({r.get("sequence_id",r.get("global_user_id")) for r in rows}),
        "users":len({r.get("global_user_id") for r in rows}),
        "sources":dict(Counter(r.get("source","legacy_synthetic") for r in rows)),
        "templates":len({r.get("template_family","unknown") for r in rows}),
        "template_distribution":dict(Counter(r.get("template_family","unknown") for r in rows)),
        "layout":dict(Counter(r.get("layout","multi_turn") for r in rows)),
        "labels":{k:dict(Counter(str(r.get(k)) for r in rows)) for k in
                  ("intent_label","selected_agent","next_action_label")},
        "unique_texts":len(set(texts)),
        "text_duplicate_rate":1-len(set(texts))/len(texts) if texts else 0,
        "sequence_lengths":dict(Counter(Counter(r.get("sequence_id",r.get("global_user_id")) for r in rows).values())),
    }


def inspect_source(path, source, *, text_field=None):
    if str(path).endswith(".parquet"):
        import pyarrow.parquet as pq
        rows=pq.read_table(path).to_pylist()
    else:
        rows=read_rows(path)
    field=text_field or ("utt" if source=="massive" else "question")
    return rows, {"rows":len(rows),"fields":sorted({k for r in rows for k in r}),
                  "source_labels":dict(Counter(str(r.get("intent",r.get("type"))) for r in rows)),
                  "source_splits":dict(Counter(r.get("partition","unknown") for r in rows)),
                  "pii_flags":dict(Counter(reason for r in rows for reason in pii_reasons(str(r.get(field,""))))),
                  "samples":[{field:redact(str(r.get(field,"")))[:250],"label":r.get("intent",r.get("type"))}
                             for r in random.Random(20260929).sample(rows,min(5,len(rows)))]}


def import_source(rows, source, revision, mapping=None, *, source_split="train", text_field=None):
    """Never infer missing agent/action/state. One source utterance = one sequence."""
    accepted, rejected, seen = [],Counter(),set()
    approved=bool(mapping and mapping.get("review_status")=="approved" and mapping.get("reviewer"))
    for index,row in enumerate(rows):
        content=row.get(text_field or ("utt" if source=="massive" else "question"))
        if not isinstance(content,str) or not content.strip():
            rejected["missing_text"]+=1; continue
        if source=="massive" and row.get("locale")!="vi-VN":
            rejected["not_vi_VN"]+=1; continue
        if row.get("partition",source_split)!=source_split:
            rejected["reserved_source_split"]+=1; continue
        if len(content)>3000:
            rejected["too_long"]+=1; continue
        if pii_reasons(content + " " + str(row.get("answer",""))):
            rejected["pii_flagged"]+=1; continue
        if norm(content) in seen:
            rejected["duplicate_text"]+=1; continue
        seen.add(norm(content))
        source_label=row.get("intent",row.get("type"))
        match=(mapping or {}).get("mappings",{}).get(source_label)
        if source=="massive" and not match:
            rejected["unmapped_intent"]+=1; continue
        uid=f"{source}-{source_split}-{row.get('id',index)}"
        accepted.append(dict(event_id=uid,global_user_id=uid,sequence_id=uid,session_id=uid,
            event_time_utc="2026-01-01T00:00:00Z",platform="web",event_type="message",content=content.strip(),
            intent_label=match["intent"] if approved and match else None,selected_agent=None,next_action_label=None,
            feedback_value=0.0,source=source,source_revision=revision,source_record_id=str(row.get("id",index)),
            source_intent=source_label,layout="single_turn",state_annotation=None,
            label_provenance="reviewed_mapping" if approved else "pending_review",
            template_family=f"external-{source}-{source_label}",partition="train_candidate"))
    return accepted, {"received":len(rows),"accepted":len(accepted),"rejected":sum(rejected.values()),
                      "reasons":dict(rejected),"mapping_approved":approved,
                      "trainable":sum(r["intent_label"] is not None for r in accepted),"stats":statistics(accepted)}


def validate_training(rows):
    if not rows:
        raise ValueError("empty training partition")
    ids=set(); times={}; users_by_seq={}
    for row in rows:
        if row.get("partition") in ("holdout","test") or "expected_intent" in row or "case_id" in row:
            raise ValueError("holdout/benchmark cannot enter training")
        required=("event_id","global_user_id","sequence_id","content","platform","event_time_utc","source","template_family")
        if any(not row.get(key) for key in required):
            raise ValueError("missing required training field")
        if row["event_id"] in ids:
            raise ValueError("duplicate event_id")
        ids.add(row["event_id"])
        if row["platform"] not in PLATFORMS or pii_reasons(row["content"]):
            raise ValueError("invalid platform or flagged PII")
        for key,allowed in (("intent_label",INTENTS),("selected_agent",AGENTS),("next_action_label",NEXT_ACTIONS)):
            if row.get(key) is not None and row[key] not in allowed:
                raise ValueError(f"invalid {key}")
        if all(row.get(key) is None for key in ("intent_label","selected_agent","next_action_label")):
            raise ValueError("unlabelled record: review before training")
        seq=row["sequence_id"]; timestamp=datetime.fromisoformat(row["event_time_utc"].replace("Z","+00:00"))
        if seq in times and timestamp<=times[seq]:
            raise ValueError("out-of-order sequence time")
        if seq in users_by_seq and users_by_seq[seq]!=row["global_user_id"]:
            raise ValueError("sequence mixes users")
        times[seq]=timestamp; users_by_seq[seq]=row["global_user_id"]
    return statistics(rows)


def assert_disjoint(partitions):
    """Fail closed on user/sequence/template or complete sequence-text overlap."""
    seen={key:set() for key in ("global_user_id","sequence_id","template_family","sequence_text")}
    for name,rows in partitions.items():
        grouped=defaultdict(list)
        for r in rows:
            grouped[r["sequence_id"]].append(norm(r.get("content",r.get("user_message",""))))
        values={key:{r[key] for r in rows} for key in ("global_user_id","sequence_id","template_family")}
        values["sequence_text"]={tuple(texts) for texts in grouped.values()}
        for key,current in values.items():
            if current & seen[key]:
                raise ValueError(f"{name}: overlapping {key}")
            seen[key].update(current)


def lock_holdout(path, manifest_path, *, seed, excluded_paths=()):
    """Write-once lock. No predictions or checkpoint is loaded by this function."""
    path, manifest_path=Path(path),Path(manifest_path)
    if manifest_path.exists():
        raise ValueError("holdout already locked; create a new version instead")
    rows=read_rows(path)
    from .personalization_benchmark import read_pilot
    read_pilot(path)
    manifest={"status":"labels_locked_not_independently_reviewed","seed":seed,
              "locked_at_utc":datetime.now(timezone.utc).isoformat(),
              "sha256":sha256(path),"file":path.name,"events":len(rows),
              "sequence_ids":sorted({r["sequence_id"] for r in rows}),
              "users":sorted({r["global_user_id"] for r in rows}),
              "template_families":sorted({r["template_family"] for r in rows}),
              "excluded":{Path(p).name:sha256(p) for p in excluded_paths}}
    manifest_path.write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding="utf-8")
    return manifest


def verify_lock(path, manifest_path):
    manifest=json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    if manifest["sha256"] != sha256(path) or not manifest["status"].startswith("labels_locked"):
        raise ValueError("holdout labels changed or not locked")
    return manifest
