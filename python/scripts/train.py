from __future__ import annotations
import argparse
import hashlib
import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
import yaml
from sklearn.metrics import f1_score
from torch import nn
from torch.utils.data import DataLoader

from dusnx_core.checkpoint import save_checkpoint
from dusnx_core.config import ModelConfig
from dusnx_core.constants import INTENTS, AGENTS, NEXT_ACTIONS
from dusnx_core.dataset import (
    FEEDBACK_CONTRACT_VERSION,
    SequenceWindowDataset,
    group_sorted,
    read_jsonl,
    split_users,
)
from dusnx_core.model import DUSNXModel


def set_seed(seed: int):
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    if torch.cuda.is_available(): torch.cuda.manual_seed_all(seed)


def build_training_metadata(data_path: str | Path, config_path: str | Path, seed: int) -> dict:
    dataset = Path(data_path)
    digest = hashlib.sha256()
    with dataset.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "seed": seed,
        "data": str(data_path),
        "dataset_sha256": digest.hexdigest(),
        "config": str(config_path),
        "feedback_contract": FEEDBACK_CONTRACT_VERSION,
        "trained_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def run_epoch(model, loader, device, optimizer=None, *, accumulation_steps=1, use_amp=False):
    train = optimizer is not None
    model.train(train)
    ce = nn.CrossEntropyLoss()
    scaler = torch.amp.GradScaler("cuda", enabled=train and use_amp)
    total_loss = 0.0
    ys_i=[]; ps_i=[]; ys_a=[]; ps_a=[]; ys_n=[]; ps_n=[]
    if train:
        optimizer.zero_grad(set_to_none=True)
    for step, batch in enumerate(loader, start=1):
        data = {k: v.to(device) for k, v in batch.items()}
        with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=use_amp):
            out, _ = model(data["token_ids"], data["platform_ids"], data["event_type_ids"], data["time_gap"], data["feedback"], data.get("valid_mask"))
            raw_loss = ce(out["intent_logits"], data["intent"]) + ce(out["router_logits"], data["agent"]) + ce(out["next_action_logits"], data["next_action"])
            loss = raw_loss / accumulation_steps
        if train:
            scaler.scale(loss).backward()
            should_step = step % accumulation_steps == 0 or step == len(loader)
            if should_step:
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad(set_to_none=True)
        total_loss += float(raw_loss.detach().cpu()) * data["intent"].shape[0]
        ys_i += data["intent"].cpu().tolist(); ps_i += out["intent_logits"].argmax(-1).cpu().tolist()
        ys_a += data["agent"].cpu().tolist(); ps_a += out["router_logits"].argmax(-1).cpu().tolist()
        ys_n += data["next_action"].cpu().tolist(); ps_n += out["next_action_logits"].argmax(-1).cpu().tolist()
    n = max(1, len(loader.dataset))
    return {
        "loss": total_loss/n,
        "intent_macro_f1": f1_score(ys_i, ps_i, average="macro", zero_division=0),
        "router_macro_f1": f1_score(ys_a, ps_a, average="macro", zero_division=0),
        "next_action_macro_f1": f1_score(ys_n, ps_n, average="macro", zero_division=0),
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/smoke.yaml")
    ap.add_argument("--data", default=None)
    args=ap.parse_args()
    cfg_raw=yaml.safe_load(Path(args.config).read_text(encoding="utf-8"))
    seed=int(cfg_raw.get("seed",42)); set_seed(seed)
    data_path=args.data or cfg_raw["data"]
    training_metadata = build_training_metadata(data_path, args.config, seed)
    rows=read_jsonl(data_path)
    users=sorted(group_sorted(rows).keys())
    tr_u, va_u, te_u = split_users(users, seed=seed, train=cfg_raw.get("train_ratio",0.8), val=cfg_raw.get("val_ratio",0.1))
    model_cfg=ModelConfig.from_dict(cfg_raw.get("model",{}))
    seq=int(cfg_raw.get("sequence_len",12)); stride=int(cfg_raw.get("stride",4))
    tr=SequenceWindowDataset(rows, model_cfg, seq, stride, set(tr_u))
    va=SequenceWindowDataset(rows, model_cfg, seq, stride, set(va_u))
    te=SequenceWindowDataset(rows, model_cfg, seq, stride, set(te_u))
    print(f"users train/val/test={len(tr_u)}/{len(va_u)}/{len(te_u)} samples={len(tr)}/{len(va)}/{len(te)}")
    device="cuda" if torch.cuda.is_available() and cfg_raw.get("device","auto") != "cpu" else "cpu"
    print("device=",device)
    model=DUSNXModel(model_cfg).to(device)
    print("parameters=",sum(p.numel() for p in model.parameters()))
    opt=torch.optim.AdamW(model.parameters(), lr=float(cfg_raw.get("learning_rate",3e-4)), weight_decay=1e-4)
    batch=int(cfg_raw.get("batch_size",32))
    accumulation_steps=max(1,int(cfg_raw.get("gradient_accumulation_steps",1)))
    use_amp=bool(cfg_raw.get("mixed_precision",True)) and device=="cuda"
    print(f"batch_size={batch} accumulation_steps={accumulation_steps} effective_batch={batch*accumulation_steps} mixed_precision={use_amp}")
    tr_loader=DataLoader(tr,batch_size=batch,shuffle=True,num_workers=0)
    va_loader=DataLoader(va,batch_size=batch,shuffle=False,num_workers=0)
    te_loader=DataLoader(te,batch_size=batch,shuffle=False,num_workers=0)
    best=-1; patience=0; best_path=cfg_raw.get("checkpoint","artifacts/dusnx_smoke.pt")
    Path(best_path).parent.mkdir(parents=True, exist_ok=True)
    for epoch in range(1,int(cfg_raw.get("epochs",5))+1):
        tm=run_epoch(model,tr_loader,device,opt,accumulation_steps=accumulation_steps,use_amp=use_amp)
        vm=run_epoch(model,va_loader,device,use_amp=use_amp)
        score=(vm["intent_macro_f1"]+vm["router_macro_f1"]+vm["next_action_macro_f1"])/3
        print(f"epoch={epoch} train={tm} val={vm} score={score:.4f}")
        if score>best:
            best=score; patience=0
            save_checkpoint(best_path,model,model_cfg,{
                **training_metadata,
                "best_val_score":best,
                "epoch":epoch,
            })
        else:
            patience+=1
            if patience>=int(cfg_raw.get("early_stopping_patience",3)):
                print("early stop")
                break
    from dusnx_core.checkpoint import load_checkpoint
    best_model, _, meta=load_checkpoint(best_path,device)
    testm=run_epoch(best_model,te_loader,device,use_amp=use_amp)
    print("TEST",json.dumps(testm,indent=2))
    metrics_path=str(Path(best_path).with_suffix(".metrics.json"))
    Path(metrics_path).write_text(json.dumps({"metadata":meta,"test":testm},indent=2),encoding="utf-8")
    print("checkpoint:",best_path)

if __name__=="__main__": main()
