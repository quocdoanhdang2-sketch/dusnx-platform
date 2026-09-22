from __future__ import annotations
import argparse, json
from pathlib import Path
import torch, yaml
from torch.utils.data import DataLoader

from dusnx_core.checkpoint import load_checkpoint
from dusnx_core.dataset import read_jsonl, group_sorted, split_users, SequenceWindowDataset
from train import run_epoch


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--checkpoint",required=True); ap.add_argument("--config",default="configs/smoke.yaml"); ap.add_argument("--data",default=None); args=ap.parse_args()
    cfg=yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    device="cuda" if torch.cuda.is_available() and cfg.get("device","auto")!="cpu" else "cpu"
    model, model_cfg, meta=load_checkpoint(args.checkpoint,device)
    rows=read_jsonl(args.data or cfg["data"]); users=sorted(group_sorted(rows).keys())
    _,_,te_u=split_users(users,seed=int(cfg.get("seed",42)),train=cfg.get("train_ratio",0.8),val=cfg.get("val_ratio",0.1))
    ds=SequenceWindowDataset(rows,model_cfg,int(cfg.get("sequence_len",12)),int(cfg.get("stride",4)),set(te_u))
    metrics=run_epoch(model,DataLoader(ds,batch_size=int(cfg.get("batch_size",32))),device)
    print(json.dumps({"metadata":meta,"metrics":metrics},indent=2,ensure_ascii=False))
if __name__=="__main__": main()
