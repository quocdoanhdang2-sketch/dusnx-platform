from pathlib import Path
import torch

from .config import ModelConfig
from .model import DUSNXModel


def save_checkpoint(path, model, cfg, metadata=None):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "model_state": model.state_dict(),
        "model_config": cfg.to_dict(),
        "metadata": metadata or {},
    }, path)


def load_checkpoint(path, device="cpu"):
    ckpt = torch.load(path, map_location=device)
    cfg = ModelConfig.from_dict(ckpt["model_config"])
    model = DUSNXModel(cfg)
    model.load_state_dict(ckpt["model_state"])
    model.to(device)
    model.eval()
    return model, cfg, ckpt.get("metadata", {})
