from pathlib import Path
import hashlib
import json
import torch

from .config import ModelConfig
from .constants import INTENTS, AGENTS, NEXT_ACTIONS
from .model import DUSNXModel


class CheckpointIncompatibleError(ValueError):
    """Raised when a checkpoint is corrupt or incompatible with model architecture/vocab."""
    pass


def validate_checkpoint_compatibility(path_or_dict, expected_cfg: ModelConfig | None = None) -> dict:
    """Verify that a checkpoint conforms to current vocabularies, heads, and dimensions."""
    if isinstance(path_or_dict, (str, Path)):
        p = Path(path_or_dict)
        if not p.is_file():
            raise CheckpointIncompatibleError(f"Checkpoint file not found: {p}")
        ckpt = torch.load(p, map_location="cpu", weights_only=False)
    elif isinstance(path_or_dict, dict):
        ckpt = path_or_dict
    else:
        raise CheckpointIncompatibleError(f"Invalid checkpoint input type: {type(path_or_dict)}")

    if "model_state" not in ckpt or "model_config" not in ckpt:
        raise CheckpointIncompatibleError("Checkpoint missing 'model_state' or 'model_config' keys")

    cfg_dict = ckpt["model_config"]
    cfg = ModelConfig.from_dict(cfg_dict)
    state = ckpt["model_state"]

    # Verify head dimensions against current label space
    if "intent_head.weight" in state:
        num_intents = state["intent_head.weight"].shape[0]
        if num_intents != len(INTENTS):
            raise CheckpointIncompatibleError(
                f"Checkpoint intent head has {num_intents} classes, but INTENTS vocabulary has {len(INTENTS)}: {INTENTS}"
            )
    else:
        raise CheckpointIncompatibleError("Missing 'intent_head.weight' in model_state")

    if "router_head.weight" in state:
        num_agents = state["router_head.weight"].shape[0]
        if num_agents != len(AGENTS):
            raise CheckpointIncompatibleError(
                f"Checkpoint router head has {num_agents} classes, but AGENTS vocabulary has {len(AGENTS)}: {AGENTS}"
            )
    else:
        raise CheckpointIncompatibleError("Missing 'router_head.weight' in model_state")

    if "next_action_head.weight" in state:
        num_actions = state["next_action_head.weight"].shape[0]
        if num_actions != len(NEXT_ACTIONS):
            raise CheckpointIncompatibleError(
                f"Checkpoint action head has {num_actions} classes, but NEXT_ACTIONS vocabulary has {len(NEXT_ACTIONS)}: {NEXT_ACTIONS}"
            )
    else:
        raise CheckpointIncompatibleError("Missing 'next_action_head.weight' in model_state")

    # Verify state dimensions
    combined = cfg.global_state_dim + cfg.platform_state_dim + cfg.task_state_dim
    if "shared.0.weight" in state:
        if state["shared.0.weight"].shape[1] != combined:
            raise CheckpointIncompatibleError(
                f"State dimensions mismatch: shared layer expects {combined} inputs, but got {state['shared.0.weight'].shape[1]}"
            )
    else:
        raise CheckpointIncompatibleError("Missing 'shared.0.weight' in model_state")

    # Verify token embedding dimensions
    if "encoder.token_emb.weight" in state:
        emb_shape = state["encoder.token_emb.weight"].shape
        if emb_shape[0] != cfg.vocab_size:
            raise CheckpointIncompatibleError(
                f"Embedding vocab size {emb_shape[0]} does not match config vocab_size {cfg.vocab_size}"
            )
        if emb_shape[1] != cfg.token_dim:
            raise CheckpointIncompatibleError(
                f"Embedding token_dim {emb_shape[1]} does not match config token_dim {cfg.token_dim}"
            )
    else:
        raise CheckpointIncompatibleError("Missing 'encoder.token_emb.weight' in model_state")

    if expected_cfg is not None:
        if cfg.to_dict() != expected_cfg.to_dict():
            raise CheckpointIncompatibleError("Checkpoint config does not match expected ModelConfig")

    metadata = ckpt.get("metadata", {})
    return {
        "compatible": True,
        "vocab_size": cfg.vocab_size,
        "num_intents": len(INTENTS),
        "num_agents": len(AGENTS),
        "num_actions": len(NEXT_ACTIONS),
        "combined_state_dim": combined,
        "metadata": metadata,
    }


def save_checkpoint(path, model, cfg, metadata=None):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    torch.save({
        "model_state": model.state_dict(),
        "model_config": cfg.to_dict(),
        "metadata": metadata or {},
    }, path)


def load_checkpoint(path, device="cpu", validate=True):
    ckpt = torch.load(path, map_location=device, weights_only=False)
    if validate:
        validate_checkpoint_compatibility(ckpt)
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
