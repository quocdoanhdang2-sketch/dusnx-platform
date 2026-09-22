import torch
from dusnx_core.config import ModelConfig
from dusnx_core.model import DUSNXModel


def test_shapes():
    cfg=ModelConfig(vocab_size=1024,max_tokens=8,token_dim=16,platform_dim=4,event_type_dim=4,event_hidden=32,global_state_dim=24,platform_state_dim=20,task_state_dim=20)
    m=DUSNXModel(cfg)
    B,L,T=2,3,8
    out,state=m(
        torch.randint(0,1024,(B,L,T)),
        torch.randint(0,3,(B,L)),
        torch.randint(0,6,(B,L)),
        torch.rand(B,L,1),
        torch.rand(B,L,1)*2-1,
    )
    assert out["intent_logits"].shape[0]==B
    assert state.platform_states.shape[:2]==(B,3)
