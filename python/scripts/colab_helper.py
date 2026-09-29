"""Notebook helpers also exercised locally; no Colab dependency at import time."""
from pathlib import Path
import json
import subprocess
import sys
import yaml
from dusnx_core.training import environment
from dusnx_core.data_pipeline import sha256,verify_lock

BASELINE_SHA256="c1e898a0e4830f3b871026c689fa5376b776eeb015efea577d0d7008f4ba7512"


def check_environment(large=False):
    if not (3,11)<=sys.version_info[:2]<=(3,14):raise RuntimeError("Repo requires Python 3.11–3.14")
    info=environment()
    if large and not info["cuda_available"]:raise RuntimeError("No GPU: select CPU smoke or change Colab runtime to GPU")
    return info


def drive_config(project,output,*,smoke=False):
    project=Path(project);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    cfg=yaml.safe_load((project/"configs/router_colab.yaml").read_text(encoding="utf-8"))
    cfg.update(data=str(project/"runtime/prepared/train.jsonl"),
               validation_data=str(project/"runtime/prepared/validation.jsonl"),
               checkpoint=str(output/"router.pt"),require_gpu=not smoke)
    if smoke:cfg.update(device="cpu",epochs=2,batch_size=4)
    path=output/"config.yaml";path.write_text(yaml.safe_dump(cfg),encoding="utf-8")
    return path


def evaluate_pair(project,new_checkpoint,baseline,output,provider="mock"):
    """Each subprocess loads exactly one checkpoint. Missing baseline is explicit."""
    project=Path(project);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    verify_lock(project/"benchmarks/holdout_v1.jsonl",project/"benchmarks/holdout_v1.manifest.json")
    checkpoints={"new":Path(new_checkpoint)};status={}
    if baseline and Path(baseline).is_file():
        if sha256(baseline)!=BASELINE_SHA256:raise ValueError("baseline is not the checkpoint measured at 23aaa48")
        checkpoints["23aaa48"]=Path(baseline)
    else:status["23aaa48"]="unavailable: upload the original checkpoint; no invented comparison"
    for name,path in checkpoints.items():
        command=[sys.executable,"python/scripts/evaluate_personalization.py","--benchmark","benchmarks/holdout_v1.jsonl",
                 "--holdout-manifest","benchmarks/holdout_v1.manifest.json","--include-no-state",
                 "--provider",provider,"--checkpoint",str(path.resolve()),"--output-dir",str((output/name).resolve())]
        status[name]={"returncode":subprocess.run(command,cwd=project).returncode,"provider":provider}
    (output/"comparison_status.json").write_text(json.dumps(status,indent=2),encoding="utf-8")
    return status
