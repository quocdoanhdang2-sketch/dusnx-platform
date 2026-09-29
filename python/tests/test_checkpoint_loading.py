import hashlib
from pathlib import Path
import pytest
import torch

from dusnx_core.checkpoint import (
    CheckpointIncompatibleError,
    load_checkpoint,
    model_identifier,
    save_checkpoint,
    validate_checkpoint_compatibility,
)
from dusnx_core.config import ModelConfig
from dusnx_core.constants import AGENTS, INTENTS, NEXT_ACTIONS
from dusnx_core.model import DUSNXModel
import apps.ai_api.main as ai_main
from fastapi.testclient import TestClient


def test_valid_checkpoint_compatibility_and_load(tmp_path):
    cfg = ModelConfig()
    model = DUSNXModel(cfg)
    ckpt_path = tmp_path / "valid_test.pt"
    meta = {"test_key": "test_val", "epoch": 6}
    save_checkpoint(ckpt_path, model, cfg, metadata=meta)

    # Validate compatibility
    info = validate_checkpoint_compatibility(ckpt_path)
    assert info["compatible"] is True
    assert info["vocab_size"] == cfg.vocab_size
    assert info["num_intents"] == len(INTENTS)
    assert info["num_agents"] == len(AGENTS)
    assert info["num_actions"] == len(NEXT_ACTIONS)
    assert info["combined_state_dim"] == cfg.global_state_dim + cfg.platform_state_dim + cfg.task_state_dim
    assert info["metadata"]["epoch"] == 6

    # Load checkpoint
    loaded_model, loaded_cfg, loaded_meta = load_checkpoint(ckpt_path, device="cpu", validate=True)
    assert isinstance(loaded_model, DUSNXModel)
    assert loaded_cfg.to_dict() == cfg.to_dict()
    assert loaded_meta["test_key"] == "test_val"


def test_missing_checkpoint_raises():
    missing = Path("non_existent_dir_12345/missing_model.pt")
    with pytest.raises(CheckpointIncompatibleError, match="not found"):
        validate_checkpoint_compatibility(missing)


def test_missing_required_keys_raises(tmp_path):
    bad_ckpt = tmp_path / "corrupt.pt"
    torch.save({"only_some_data": 123}, bad_ckpt)
    with pytest.raises(CheckpointIncompatibleError, match="missing 'model_state' or 'model_config'"):
        validate_checkpoint_compatibility(bad_ckpt)


def test_intent_vocabulary_mismatch_raises(tmp_path):
    cfg = ModelConfig()
    model = DUSNXModel(cfg)
    state = model.state_dict()
    # Tamper with intent_head dimension (5 instead of len(INTENTS)=6)
    state["intent_head.weight"] = torch.randn(len(INTENTS) - 1, state["intent_head.weight"].shape[1])
    state["intent_head.bias"] = torch.randn(len(INTENTS) - 1)

    ckpt_path = tmp_path / "bad_intent.pt"
    torch.save({"model_state": state, "model_config": cfg.to_dict()}, ckpt_path)

    with pytest.raises(CheckpointIncompatibleError, match="Checkpoint intent head has"):
        validate_checkpoint_compatibility(ckpt_path)


def test_agent_vocabulary_mismatch_raises(tmp_path):
    cfg = ModelConfig()
    model = DUSNXModel(cfg)
    state = model.state_dict()
    # Tamper with router_head dimension (5 instead of len(AGENTS)=3)
    state["router_head.weight"] = torch.randn(len(AGENTS) + 2, state["router_head.weight"].shape[1])
    state["router_head.bias"] = torch.randn(len(AGENTS) + 2)

    ckpt_path = tmp_path / "bad_agent.pt"
    torch.save({"model_state": state, "model_config": cfg.to_dict()}, ckpt_path)

    with pytest.raises(CheckpointIncompatibleError, match="Checkpoint router head has"):
        validate_checkpoint_compatibility(ckpt_path)


def test_action_vocabulary_mismatch_raises(tmp_path):
    cfg = ModelConfig()
    model = DUSNXModel(cfg)
    state = model.state_dict()
    # Tamper with next_action_head dimension
    state["next_action_head.weight"] = torch.randn(len(NEXT_ACTIONS) + 1, state["next_action_head.weight"].shape[1])
    state["next_action_head.bias"] = torch.randn(len(NEXT_ACTIONS) + 1)

    ckpt_path = tmp_path / "bad_action.pt"
    torch.save({"model_state": state, "model_config": cfg.to_dict()}, ckpt_path)

    with pytest.raises(CheckpointIncompatibleError, match="Checkpoint action head has"):
        validate_checkpoint_compatibility(ckpt_path)


def test_state_dimension_mismatch_raises(tmp_path):
    cfg = ModelConfig()
    model = DUSNXModel(cfg)
    state = model.state_dict()
    # Tamper with shared.0.weight input dimension
    state["shared.0.weight"] = torch.randn(state["shared.0.weight"].shape[0], 256)

    ckpt_path = tmp_path / "bad_state.pt"
    torch.save({"model_state": state, "model_config": cfg.to_dict()}, ckpt_path)

    with pytest.raises(CheckpointIncompatibleError, match="State dimensions mismatch"):
        validate_checkpoint_compatibility(ckpt_path)


def test_token_embedding_vocab_mismatch_raises(tmp_path):
    cfg = ModelConfig(vocab_size=16384)
    model = DUSNXModel(cfg)
    state = model.state_dict()
    # Tamper with embedding vocab size
    state["encoder.token_emb.weight"] = torch.randn(1000, cfg.token_dim)

    ckpt_path = tmp_path / "bad_emb.pt"
    torch.save({"model_state": state, "model_config": cfg.to_dict()}, ckpt_path)

    with pytest.raises(CheckpointIncompatibleError, match="Embedding vocab size"):
        validate_checkpoint_compatibility(ckpt_path)


def test_fastapi_load_model_and_health_integration(tmp_path):
    client = TestClient(ai_main.app)

    # 1. Missing checkpoint fallback
    missing_path = tmp_path / "missing.pt"
    ai_main.load_model(missing_path)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["checkpoint_loaded"] is False
    assert data["model_loaded"] is False
    assert data["runtime_mode"] == "bootstrap_rules"
    assert "not found" in data["metadata"]["warning"]

    # 2. Corrupt checkpoint fallback
    corrupt_path = tmp_path / "corrupt.pt"
    torch.save({"random_data": [1, 2, 3]}, corrupt_path)
    ai_main.load_model(corrupt_path)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["checkpoint_loaded"] is False
    assert data["model_loaded"] is False
    assert data["runtime_mode"] == "bootstrap_rules"
    assert "CheckpointIncompatibleError" in data["metadata"]["warning"]

    # 3. Valid checkpoint load
    valid_path = tmp_path / "valid.pt"
    cfg = ModelConfig()
    model = DUSNXModel(cfg)
    save_checkpoint(valid_path, model, cfg, metadata={"epoch": 6, "val_score": 0.85})
    ai_main.load_model(valid_path)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["checkpoint_loaded"] is True
    assert data["model_loaded"] is True
    assert data["runtime_mode"] == "trained_dusnx"
    assert data["checkpoint_path"] == str(valid_path.resolve())
    assert "checkpoint:" in data["model_version"]


def test_colab_checkpoint_verification_if_present():
    colab_ckpt = Path("training-results/colab-run-01/extracted/dusnx-router-full-01/router.pt")
    if not colab_ckpt.is_file():
        pytest.skip("Colab checkpoint not present in local working tree")

    sha256 = hashlib.sha256(colab_ckpt.read_bytes()).hexdigest()
    assert sha256 == "56f56e6d61afc264fb02d690d2872fb3ac5db9749a659c8493fd9d99eab7e7b1"

    info = validate_checkpoint_compatibility(colab_ckpt)
    assert info["compatible"] is True
    assert info["metadata"]["epoch"] == 6
    assert info["metadata"]["commit_sha"] == "50e1042aa45ca99d17c989817a08a0896f7a7935"
