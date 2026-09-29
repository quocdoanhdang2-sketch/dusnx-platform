"""Train DUSN-X recurrent state cells and classification heads, never an LLM."""
from __future__ import annotations
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import sys

import numpy as np
import torch
from sklearn.metrics import f1_score
from torch.utils.data import DataLoader
import yaml

from .checkpoint import load_checkpoint, save_checkpoint
from .config import ModelConfig
from .constants import INTENTS, AGENTS, NEXT_ACTIONS
from .data_pipeline import assert_disjoint, sha256, validate_training
from .dataset import FEEDBACK_CONTRACT_VERSION, SequenceWindowDataset, read_jsonl, split_users
from .model import DUSNXModel

LABELS={"intent":INTENTS,"agent":AGENTS,"next_action":NEXT_ACTIONS}
LOGITS={"intent":"intent_logits","agent":"router_logits","next_action":"next_action_logits"}


def set_seed(seed):
    random.seed(seed);np.random.seed(seed);torch.manual_seed(seed)
    if torch.cuda.is_available():torch.cuda.manual_seed_all(seed)


def build_training_metadata(data_path,config_path,seed):
    return dict(seed=seed,data=str(data_path),dataset_sha256=sha256(data_path),config=str(config_path),
                feedback_contract=FEEDBACK_CONTRACT_VERSION,
                trained_at_utc=datetime.now(timezone.utc).isoformat().replace("+00:00","Z"))


def masked_loss(logits,target):
    mask=target!=-100
    return torch.nn.functional.cross_entropy(logits[mask],target[mask]) if mask.any() else logits.sum()*0


def run_epoch(model,loader,device,optimizer=None,*,accumulation_steps=1,use_amp=False,scaler=None):
    train=optimizer is not None
    model.train(train)
    scaler=scaler or torch.amp.GradScaler("cuda",enabled=train and use_amp)
    expected={k:[] for k in LABELS};predicted={k:[] for k in LABELS}
    total=0.0;count=0
    if train:optimizer.zero_grad(set_to_none=True)
    for index,batch in enumerate(loader):
        data={k:v.to(device) for k,v in batch.items()}
        with torch.set_grad_enabled(train), torch.autocast(device_type="cuda",dtype=torch.float16,enabled=use_amp):
            out,_=model(data["token_ids"],data["platform_ids"],data["event_type_ids"],data["time_gap"],data["feedback"],data["valid_mask"])
            raw=sum(masked_loss(out[LOGITS[k]],data[k]) for k in LABELS)
            # The final short accumulation group must not be underweighted.
            group_start=(index//accumulation_steps)*accumulation_steps
            divisor=min(accumulation_steps,len(loader)-group_start)
            loss=raw/divisor
        if train:
            scaler.scale(loss).backward()
            if (index+1)%accumulation_steps==0 or index+1==len(loader):
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(),1.0)
                scaler.step(optimizer);scaler.update();optimizer.zero_grad(set_to_none=True)
        n=data["intent"].shape[0];total+=float(raw.detach().cpu())*n;count+=n
        for key in LABELS:
            mask=data[key]!=-100
            expected[key]+=data[key][mask].detach().cpu().tolist()
            predicted[key]+=out[LOGITS[key]].argmax(-1)[mask].detach().cpu().tolist()
    result={"loss":total/max(count,1),"samples":count}
    for key,name in (("intent","intent"),("agent","router"),("next_action","next_action")):
        result[name+"_macro_f1"]=float(f1_score(expected[key],predicted[key],labels=list(range(len(LABELS[key]))),
                                                average="macro",zero_division=0)) if expected[key] else 0.0
        result[name+"_labelled"]=len(expected[key])
    return result


def environment():
    return dict(python=sys.version.split()[0],torch=str(torch.__version__),cuda_available=torch.cuda.is_available(),
                gpu=torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
                gpu_memory_gb=round(torch.cuda.get_device_properties(0).total_memory/2**30,2) if torch.cuda.is_available() else 0)


def choose_batch(requested,device,*,smoke=False):
    if device=="cpu":return min(requested,8 if smoke else 16)
    free,_=torch.cuda.mem_get_info()
    # Conservative initial choice, not a promise of fitting arbitrary models.
    cap=8 if free<4*2**30 else 16 if free<8*2**30 else 32 if free<16*2**30 else 64
    return min(requested,cap)


def rng_state():
    state=np.random.get_state()
    return dict(python=random.getstate(),numpy=[state[0],state[1].tolist(),state[2],state[3],state[4]],
                torch=torch.get_rng_state(),cuda=torch.cuda.get_rng_state_all() if torch.cuda.is_available() else [])


def restore_rng(state):
    random.setstate(state["python"])
    n=state["numpy"];np.random.set_state((n[0],np.asarray(n[1],dtype=np.uint32),n[2],n[3],n[4]))
    torch.set_rng_state(state["torch"].cpu())
    if torch.cuda.is_available() and state["cuda"]:torch.cuda.set_rng_state_all(state["cuda"])


def atomic_save(payload,path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+".tmp")
    torch.save(payload,temporary);temporary.replace(path)


def train(config_path,*,data=None,resume=None,init_from=None,epochs=None,checkpoint=None,device=None,smoke=False):
    cfg=yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    if data:cfg["data"]=str(data)
    if epochs is not None:cfg["epochs"]=epochs
    if checkpoint:cfg["checkpoint"]=str(checkpoint)
    if device:cfg["device"]=device
    if resume and init_from:raise ValueError("resume and init-from are mutually exclusive")
    env=environment()
    selected="cuda" if torch.cuda.is_available() and cfg.get("device","auto")!="cpu" else "cpu"
    if cfg.get("device")=="cuda" and selected!="cuda":raise ValueError("CUDA requested but unavailable; select CPU smoke")
    if selected=="cpu" and cfg.get("require_gpu",False) and not smoke:
        raise ValueError("Large training requires GPU; select smoke config or explicitly disable require_gpu")
    torch.set_num_threads(int(cfg.get("cpu_threads",2)))
    seed=int(cfg.get("seed",42));set_seed(seed)
    rows=read_jsonl(cfg["data"])
    meta=build_training_metadata(cfg["data"],config_path,seed)
    if cfg.get("validation_data"):
        val_rows=read_jsonl(cfg["validation_data"])
        validate_training(rows);validate_training(val_rows)
        assert_disjoint({"train":rows,"validation":val_rows})
        meta["validation_sha256"]=sha256(cfg["validation_data"])
        training_rows=rows
        test_rows=[]  # never open held-out labels during training
    else:
        users=sorted({r["global_user_id"] for r in rows})
        tr,va,te=split_users(users,seed=seed,train=cfg.get("train_ratio",.8),val=cfg.get("val_ratio",.1))
        training_rows=[r for r in rows if r["global_user_id"] in set(tr)]
        val_rows=[r for r in rows if r["global_user_id"] in set(va)]
        test_rows=[r for r in rows if r["global_user_id"] in set(te)]
    model_cfg=ModelConfig.from_dict(cfg.get("model",{}))
    sequence_len=int(cfg.get("sequence_len",8));stride=int(cfg.get("stride",1))
    train_ds=SequenceWindowDataset(training_rows,model_cfg,sequence_len,stride)
    val_ds=SequenceWindowDataset(val_rows,model_cfg,sequence_len,stride)
    if not len(train_ds) or not len(val_ds):raise ValueError("train/validation has no supervised windows")
    batch=choose_batch(int(cfg.get("batch_size",16)),selected,smoke=smoke)
    accumulation=max(1,int(cfg.get("gradient_accumulation_steps",1)))
    amp=bool(cfg.get("mixed_precision",True)) and selected=="cuda"
    cfg.update(effective_batch_size=batch,device=selected)
    contract={k:v for k,v in cfg.items() if k not in ("epochs","checkpoint","require_gpu")}
    contract_hash=hashlib.sha256(json.dumps(contract,sort_keys=True).encode()).hexdigest()
    meta.update(labels=LABELS,config_sha256=contract_hash,environment=env,training_objective="router_heads_through_recurrent_state",
                no_llm_finetuning=True,train_samples=len(train_ds),validation_samples=len(val_ds))
    model=DUSNXModel(model_cfg).to(selected)
    if init_from:
        initial,initial_cfg,_=load_checkpoint(init_from,selected)
        if initial_cfg.to_dict()!=model_cfg.to_dict():raise ValueError("init checkpoint architecture mismatch")
        model.load_state_dict(initial.state_dict());meta["init_checkpoint_sha256"]=sha256(init_from)
    optimizer=torch.optim.AdamW(model.parameters(),lr=float(cfg.get("learning_rate",.0003)),weight_decay=1e-4)
    scaler=torch.amp.GradScaler("cuda",enabled=amp)
    best=-1.;patience=0;start=1;history=[];best_state=None
    best_path=Path(cfg.get("checkpoint","artifacts/dusnx_router.pt"))
    best_path.parent.mkdir(parents=True,exist_ok=True)
    last_path=best_path.with_suffix(".last.pt")
    if resume:
        saved=torch.load(resume,map_location=selected,weights_only=True)
        for key in ("dataset_sha256","validation_sha256","config_sha256"):
            if saved["metadata"].get(key)!=meta.get(key):raise ValueError(f"resume {key} mismatch")
        if saved["metadata"]["labels"]!=LABELS:raise ValueError("resume label vocabulary mismatch")
        model.load_state_dict(saved["model_state"]);optimizer.load_state_dict(saved["optimizer_state"])
        scaler.load_state_dict(saved["scaler_state"])
        best=saved["best_score"];patience=saved["patience"];start=saved["epoch"]+1
        history=saved["history"];best_state=saved["best_model_state"];restore_rng(saved["rng_state"])
        meta=saved["metadata"]
        save_checkpoint(best_path,_model_with_state(model,best_state),model_cfg,dict(meta,best_val_score=best,epoch=saved["best_epoch"]))
        model.load_state_dict(saved["model_state"])
    elif best_path.exists() or last_path.exists():
        raise ValueError("checkpoint already exists; use --resume or a new output path")
    (best_path.with_suffix(".config.json")).write_text(json.dumps(cfg,indent=2),encoding="utf-8")
    train_loader=DataLoader(train_ds,batch_size=batch,shuffle=True,num_workers=0)
    val_loader=DataLoader(val_ds,batch_size=batch,shuffle=False,num_workers=0)
    best_epoch=history[-1].get("best_epoch",0) if history else 0
    print(json.dumps(dict(environment=env,train_windows=len(train_ds),val_windows=len(val_ds),batch=batch,accumulation=accumulation)))
    for epoch in range(start,int(cfg.get("epochs",5))+1):
        if patience>=int(cfg.get("early_stopping_patience",3)):break
        try:
            tm=run_epoch(model,train_loader,selected,optimizer,accumulation_steps=accumulation,use_amp=amp,scaler=scaler)
        except torch.cuda.OutOfMemoryError as exc:
            raise RuntimeError("GPU OOM: reduce batch_size; restart from last epoch checkpoint with matching config or start a new run") from exc
        vm=run_epoch(model,val_loader,selected,use_amp=amp)
        supported=[vm[k+"_macro_f1"] for k in ("intent","router","next_action") if vm[k+"_labelled"]]
        if not supported:raise ValueError("validation has no labels")
        score=sum(supported)/len(supported)
        if score>best:
            best=score;patience=0;best_epoch=epoch;best_state=copy.deepcopy(model.state_dict())
            save_checkpoint(best_path,model,model_cfg,dict(meta,best_val_score=best,epoch=epoch))
        else:patience+=1
        record=dict(epoch=epoch,train=tm,validation=vm,score=score,best_epoch=best_epoch)
        history.append(record);print(json.dumps(record),flush=True)
        atomic_save(dict(model_state=model.state_dict(),model_config=model_cfg.to_dict(),metadata=meta,
                         optimizer_state=optimizer.state_dict(),scaler_state=scaler.state_dict(),rng_state=rng_state(),
                         epoch=epoch,best_score=best,best_epoch=best_epoch,patience=patience,history=history,
                         best_model_state=best_state),last_path)
        best_path.with_suffix(".epochs.jsonl").write_text("".join(json.dumps(r)+"\n" for r in history),encoding="utf-8")
    best_model,_,best_meta=load_checkpoint(best_path,selected)
    result=dict(metadata=best_meta,epochs=history,validation=run_epoch(best_model,val_loader,selected),
                holdout_evaluated=False,checkpoint_sha256=sha256(best_path))
    if test_rows:
        test_ds=SequenceWindowDataset(test_rows,model_cfg,sequence_len,stride)
        result["legacy_user_split_test"]=run_epoch(best_model,DataLoader(test_ds,batch_size=batch),selected)
    best_path.with_suffix(".metrics.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    return result


def _model_with_state(model,state):
    model.load_state_dict(state)
    return model
