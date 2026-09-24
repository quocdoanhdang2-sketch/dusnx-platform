import pytest

from apps.ai_api import main
from dusnx_core.config import ModelConfig
from dusnx_core.inference import snapshot_to_state, state_reset_reason
from dusnx_core.model import DUSNXModel
from dusnx_core.schema import STATE_SCHEMA_VERSION, ProcessRequest, StateSnapshot


def cfg():
    return ModelConfig(global_state_dim=4, platform_state_dim=3, task_state_dim=5)


def snapshot(model_version="model-a", **overrides):
    values = {
        "global_state": [0.0] * 4,
        "platform_states": [[0.0] * 3 for _ in range(3)],
        "task_state": [0.0] * 5,
        "state_version": 7,
        "state_schema_version": STATE_SCHEMA_VERSION,
        "model_version": model_version,
    }
    values.update(overrides)
    return StateSnapshot(**values)


def test_compatible_state_is_converted_to_tensors():
    config = cfg()
    state = snapshot()
    converted = snapshot_to_state(state, DUSNXModel(config), config, "model-a", "cpu")
    assert converted.global_state.shape == (1, 4)
    assert converted.platform_states.shape == (1, 3, 3)
    assert converted.task_state.shape == (1, 5)


def test_v1_wrong_vector_size_is_rejected_before_tensor_creation():
    assert state_reset_reason(snapshot(global_state=[0.0] * 2), cfg(), "model-a") == "incompatible_global_state_size"
    with pytest.raises(ValueError, match="incompatible_global_state_size"):
        snapshot_to_state(snapshot(global_state=[0.0] * 2), DUSNXModel(cfg()), cfg(), "model-a", "cpu")


def test_legacy_state_without_metadata_is_reset_intentionally():
    legacy = snapshot(state_schema_version=None, model_version=None)
    assert state_reset_reason(legacy, cfg(), "model-a") == "legacy_state_missing_state_schema_version"


def test_model_change_resets_even_when_shapes_match():
    assert state_reset_reason(snapshot(model_version="model-v1"), cfg(), "model-v2") == "incompatible_model_version"


def test_request_after_reset_uses_the_new_snapshot(monkeypatch):
    config = cfg()
    monkeypatch.setattr(main, "MODEL", None)
    monkeypatch.setattr(main, "CFG", config)
    monkeypatch.setattr(main, "MODEL_VERSION", "bootstrap_rules:config-test")
    incompatible = snapshot(model_version="old-model")
    first = main.process(ProcessRequest(global_user_id="u", platform="web", content="hello", previous_state=incompatible))
    assert first.state_reset is True
    assert first.reset_reason == "incompatible_model_version"
    assert first.state_snapshot.state_version == 1
    assert first.state_snapshot.model_version == "bootstrap_rules:config-test"

    second = main.process(ProcessRequest(global_user_id="u", platform="web", content="again", previous_state=first.state_snapshot))
    assert second.state_reset is False
    assert second.reset_reason is None
    assert second.state_snapshot.state_version == 2
