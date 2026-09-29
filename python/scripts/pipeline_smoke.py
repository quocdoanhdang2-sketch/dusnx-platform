"""Offline CPU test of prepare/train/resume; no external data or GPU required."""
import argparse
import json
from pathlib import Path
import sys
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
for path in (REPO_ROOT / "python/src", REPO_ROOT / "python", REPO_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dusnx_core.designed_data import generate_designed
from dusnx_core.data_pipeline import write_rows,validate_training,assert_disjoint
from dusnx_core.training import train


def smoke(output):
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    parts=generate_designed(per_family=1)
    for name,rows in parts.items():validate_training(rows);write_rows(out/f"{name}.jsonl",rows)
    assert_disjoint(parts)
    cfg=dict(seed=17,data=str(out/"train.jsonl"),validation_data=str(out/"validation.jsonl"),
        checkpoint=str(out/"smoke.pt"),device="cpu",epochs=1,batch_size=4,sequence_len=4,stride=1,
        gradient_accumulation_steps=3,early_stopping_patience=3,model=dict(vocab_size=256,max_tokens=12,
        token_dim=8,platform_dim=4,event_type_dim=4,event_hidden=16,global_state_dim=12,
        platform_state_dim=8,task_state_dim=8,dropout=0.0))
    path=out/"config.yaml";path.write_text(yaml.safe_dump(cfg),encoding="utf-8")
    train(path,smoke=True)
    result=train(path,resume=out/"smoke.last.pt",epochs=2,smoke=True)
    assert len(result["epochs"])==2 and result["holdout_evaluated"] is False
    return result


if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--output",default="runtime/pipeline-smoke")
    print(json.dumps(smoke(ap.parse_args().output)["validation"]))
