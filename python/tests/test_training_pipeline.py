import json
from pathlib import Path
import torch
import pytest
from dusnx_core.training import train
from dusnx_core.data_pipeline import read_rows, write_rows
from python.scripts.pipeline_smoke import smoke
from python.scripts.colab_helper import check_environment,drive_config


def test_resume_matches_uninterrupted_and_updates_state_cells(tmp_path):
    result=smoke(tmp_path/"resumed")
    config=tmp_path/"resumed/config.yaml"
    result2=train(config,epochs=2,checkpoint=tmp_path/"full.pt",smoke=True)
    left=torch.load(tmp_path/"resumed/smoke.last.pt",weights_only=True)
    right=torch.load(tmp_path/"full.last.pt",weights_only=True)
    for key,value in left["model_state"].items():assert torch.equal(value,right["model_state"][key]),key
    assert result["epochs"]==result2["epochs"]
    from dusnx_core.training import set_seed
    from dusnx_core.config import ModelConfig
    from dusnx_core.model import DUSNXModel
    set_seed(17)
    initial=DUSNXModel(ModelConfig.from_dict(left["model_config"])).state_dict()
    for cell in ("global_cell","platform_cell","task_cell"):
        assert not torch.equal(initial[cell+".candidate.weight"],left["model_state"][cell+".candidate.weight"])
    rows=read_rows(tmp_path/"resumed/train.jsonl")
    rows[0]["content"]+=" changed"
    write_rows(tmp_path/"resumed/train.jsonl",rows)
    with pytest.raises(ValueError,match="dataset_sha256"):
        train(config,resume=tmp_path/"resumed/smoke.last.pt",epochs=3,smoke=True)


def test_colab_helpers_cpu_and_config(tmp_path,monkeypatch):
    import python.scripts.colab_helper as helper
    monkeypatch.setattr(helper,"environment",lambda:{"cuda_available":False})
    with pytest.raises(RuntimeError,match="No GPU"):check_environment(large=True)
    path=drive_config(Path.cwd(),tmp_path,smoke=True)
    assert path.is_file()
