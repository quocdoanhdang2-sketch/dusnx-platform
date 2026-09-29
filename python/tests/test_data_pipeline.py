import copy
import json
from pathlib import Path
import pytest
import torch
from dusnx_core.data_pipeline import *
from dusnx_core.designed_data import generate_designed,make_holdout
from dusnx_core.review import review_sample,agreement
from dusnx_core.training import masked_loss
from dusnx_core.dataset import SequenceWindowDataset
from dusnx_core.config import ModelConfig


def test_split_integrity_and_training_rejects_holdout():
    parts=generate_designed(per_family=1)
    assert_disjoint({**parts,"holdout":make_holdout()})
    for rows in parts.values():validate_training(rows)
    with pytest.raises(ValueError,match="holdout"):validate_training(make_holdout())
    with pytest.raises(ValueError,match="overlapping"):assert_disjoint({"a":parts["train"],"b":parts["train"]})


@pytest.mark.parametrize("change,match",[
    (lambda r:r.append(dict(r[0])),"duplicate"),
    (lambda r:r[0].pop("source"),"missing required"),
    (lambda r:r[0].update(intent_label="invented"),"invalid intent"),
    (lambda r:r[1].update(event_time_utc=r[0]["event_time_utc"]),"out-of-order"),
])
def test_invalid_training_records(change,match):
    rows=generate_designed(per_family=1)["train"]
    change(rows)
    with pytest.raises(ValueError,match=match):validate_training(rows)


def test_filter_and_partial_labels_require_mapping_review():
    source=[dict(id=i,utt=text,locale="vi-VN",partition="train",intent="greet") for i,text in enumerate([
        "chào bạn","chào bạn","email tôi là someone@example.test","không ánh xạ"])]
    source[-1]["intent"]="unsupported"
    mapping=dict(review_status="pending_human_review",mappings={"greet":{"intent":"chat"}})
    rows,report=import_source(source,"massive","fixed",mapping)
    assert report["accepted"]==1 and report["trainable"]==0
    mapping.update(review_status="approved",reviewer="test reviewer")
    rows,report=import_source(source,"massive","fixed",mapping)
    assert report["trainable"]==1
    assert rows[0]["selected_agent"] is None and rows[0]["state_annotation"] is None
    ds=SequenceWindowDataset(rows,ModelConfig(),8,1)
    assert len(ds)==1 and ds[0]["agent"].item()==-100


def test_masked_head_has_zero_gradient():
    logits=torch.randn(2,3,requires_grad=True)
    loss=masked_loss(logits,torch.tensor([-100,-100]));loss.backward()
    assert torch.isfinite(loss) and torch.count_nonzero(logits.grad)==0


def test_lock_detects_tampering_and_refuses_relock(tmp_path):
    path=tmp_path/"holdout.jsonl";manifest=tmp_path/"manifest.json"
    write_rows(path,make_holdout());lock_holdout(path,manifest,seed=914207)
    verify_lock(path,manifest)
    with pytest.raises(ValueError,match="already locked"):lock_holdout(path,manifest,seed=1)
    path.write_text(path.read_text(encoding="utf-8")+"\n",encoding="utf-8")
    with pytest.raises(ValueError,match="changed"):verify_lock(path,manifest)


def test_blind_review_and_disagreement():
    template=review_sample(make_holdout(),sequences=2)
    assert all("prediction" not in r and "expected_intent" not in r for r in template)
    assert all(all(v is None for v in r["labels"].values()) for r in template)
    left=copy.deepcopy(template);right=copy.deepcopy(template)
    for rows,name in ((left,"reviewer A"),(right,"reviewer B")):
        for r in rows:r.update(reviewer=name,labels=dict(active=[],obsolete=[],intent="chat",agent="conversation",action="reply",requires_clarification=False))
    right[0]["labels"]["intent"]="followup"
    assert len(agreement(left,right)["disagreements"])==1
    with pytest.raises(ValueError,match="distinct"):agreement(left,left)


def test_notebook_code_cells_parse_without_outputs():
    import ast
    repo_root = Path(__file__).resolve().parents[2]
    notebook=json.loads((repo_root / "notebooks/train_dusnx_colab.ipynb").read_text(encoding="utf-8"))
    for cell in notebook["cells"]:
        if cell["cell_type"]=="code":
            ast.parse("".join(cell["source"]))
            assert cell["outputs"]==[]
