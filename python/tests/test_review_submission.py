import copy
import json
from pathlib import Path
import pytest
from dusnx_core.review import validate_submission,adjudicate
from python.scripts.review_labels import export_csv,import_csv,load_reviewed_records


def example():
    # Small invented fixtures only. Never read or infer labels for holdout v3.
    blind=[dict(record_id="unit-1",sequence_id="unit",step=1,platform="web",session_id="s",
                user_message="Xin chào",reviewer=None,review_date=None,notes="",
                labels={k:None for k in ("active","obsolete","intent","agent","action","requires_clarification")})]
    filled=copy.deepcopy(blind)
    filled[0].update(reviewer="unit_A",review_date="2026-09-30",labels=dict(active=[],obsolete=[],intent="chat",
                  agent="conversation",action="reply",requires_clarification=False))
    return blind,filled


def test_submission_requires_all_reference_rows_and_valid_date():
    blind,filled=example();assert validate_submission(filled,blind)==1
    with pytest.raises(ValueError):validate_submission([],blind)
    wrong=copy.deepcopy(filled);wrong[0]["user_message"]="changed"
    with pytest.raises(ValueError,match="Changed reference"):validate_submission(wrong,blind)
    wrong=copy.deepcopy(filled);wrong[0]["review_date"]="yesterday"
    with pytest.raises(ValueError,match="review_date"):validate_submission(wrong,blind)
    extra=copy.deepcopy(filled);extra[0]["record_id"]="extra"
    with pytest.raises(ValueError,match="every reference"):validate_submission(extra,blind)


def test_csv_blank_is_unreviewed_and_json_fact_lists_roundtrip(tmp_path):
    blind,filled=example();p=tmp_path/"review.csv"
    export_csv(blind,p)
    with pytest.raises(ValueError,match="unlabelled"):validate_submission(import_csv(p),blind)
    filled[0]["labels"]["active"]=["Một câu, có dấu phẩy"]
    export_csv(filled,p)
    converted=import_csv(p)
    assert converted[0]["labels"]==filled[0]["labels"]
    assert validate_submission(converted,blind)==1


def test_gold_cannot_be_mistaken_for_review_and_draft_never_self_approves(tmp_path):
    p=tmp_path/"gold.jsonl";p.write_text(json.dumps({"expected_intent":"chat"})+"\n")
    with pytest.raises(ValueError,match="Gold benchmark"):load_reviewed_records(p)
    blind,a=example();b=copy.deepcopy(a);b[0]["reviewer"]="unit_B"
    b[0]["labels"]["intent"]="followup"
    result=adjudicate(a,b,adjudicator="Human name placeholder")
    assert result["status"]=="draft_pending_human_attestation"
    assert result["records"][0]["labels"]["intent"]=="PENDING_HUMAN_RESOLUTION"


def test_review_lock_requires_attestation_and_resolved_labels(tmp_path,monkeypatch):
    import sys
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/"scripts"))
    from lock_review import freeze
    from dusnx_core.data_pipeline import write_rows,sha256
    blind,a=example();b=copy.deepcopy(a);b[0]["reviewer"]="unit_B"
    b[0]["labels"]["intent"]="followup"
    for name,rows in (("blind",blind),("a",a),("b",b)):write_rows(tmp_path/f"{name}.jsonl",rows)
    adj=adjudicate(a,b,adjudicator="Fixture person; no actual review")
    path=tmp_path/"adjudication.json";path.write_text(json.dumps(adj))
    args=(path,tmp_path/"a.jsonl",tmp_path/"b.jsonl",tmp_path/"blind.jsonl",tmp_path/"locked.jsonl")
    with pytest.raises(ValueError,match="attest"):freeze(*args)
    with pytest.raises(ValueError,match="Unresolved"):freeze(*args,attest=True)
    adj["records"][0]["labels"]["intent"]="chat"
    path.write_text(json.dumps(adj))
    meta=freeze(*args,attest=True)
    assert meta["sha256"]==sha256(tmp_path/"locked.jsonl") and not meta["evaluation_run"]
    with pytest.raises(ValueError,match="already exists"):freeze(*args,attest=True)
