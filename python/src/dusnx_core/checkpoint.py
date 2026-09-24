from pathlib import Path
import hashlib
import json
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


def model_identifier(checkpoint_path, cfg: ModelConfig, runtime_mode: str) -> str:
    """Stable identity tied to the active checkpoint bytes and model config."""
    config_bytes = json.dumps(cfg.to_dict(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    config_hash = hashlib.sha256(config_bytes).hexdigest()[:12]
    if runtime_mode == "bootstrap_rules":
        return f"bootstrap_rules:config-{config_hash}"

    checkpoint = Path(checkpoint_path)
    checkpoint_hash = hashlib.sha256(checkpoint.read_bytes()).hexdigest()[:12]
    return f"checkpoint:{checkpoint.name}:sha256-{checkpoint_hash}:config-{config_hash}"
