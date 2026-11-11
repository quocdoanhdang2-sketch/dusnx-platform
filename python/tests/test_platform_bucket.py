import torch

from dusnx_core.config import ModelConfig
from dusnx_core.inference import process_one
from dusnx_core.model import DUSNXModel
from dusnx_core.schema import ProcessRequest

CFG = ModelConfig(
    vocab_size=256, max_tokens=8, token_dim=8, platform_dim=4, event_type_dim=4,
    event_hidden=16, global_state_dim=12, platform_state_dim=8, task_state_dim=8, dropout=0.0,
)


def _run(platform: str):
    torch.manual_seed(0)
    model = DUSNXModel(CFG)
    return process_one(
        model, CFG, ProcessRequest(global_user_id="u", platform=platform, content="hello"),
        "test_model", torch.device("cpu"),
    )


def test_untrained_platform_is_classified_via_web_bucket():
    result = _run("word")
    assert result["intent"]
    assert result["selected_agent"]
    assert result["next_action"]
    assert 0.0 <= result["confidence"] <= 1.0


def test_untrained_platform_matches_web_output():
    word = _run("word")
    web = _run("web")
    assert word["intent"] == web["intent"]
    assert word["selected_agent"] == web["selected_agent"]
    assert word["next_action"] == web["next_action"]
