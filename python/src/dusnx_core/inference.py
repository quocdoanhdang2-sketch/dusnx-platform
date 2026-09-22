from __future__ import annotations
import torch

from .constants import PLATFORM_TO_ID, EVENT_TYPE_TO_ID, INTENTS, AGENTS, NEXT_ACTIONS
from .model import DusnxState
from .tokenizer import encode_text


def snapshot_to_state(snapshot, model, device):
    if snapshot is None:
        return model.initial_state(1, device)
    return DusnxState(
        global_state=torch.tensor([snapshot.global_state], dtype=torch.float32, device=device),
        platform_states=torch.tensor([snapshot.platform_states], dtype=torch.float32, device=device),
        task_state=torch.tensor([snapshot.task_state], dtype=torch.float32, device=device),
    )


def state_to_snapshot(state, version: int):
    return {
        "global_state": state.global_state[0].detach().cpu().tolist(),
        "platform_states": state.platform_states[0].detach().cpu().tolist(),
        "task_state": state.task_state[0].detach().cpu().tolist(),
        "state_version": version,
    }

@torch.inference_mode()
def process_one(model, cfg, req, device):
    token_ids = torch.tensor([encode_text(req.content, cfg.vocab_size, cfg.max_tokens)], dtype=torch.long, device=device)
    platform_ids = torch.tensor([PLATFORM_TO_ID[req.platform]], dtype=torch.long, device=device)
    event_type_ids = torch.tensor([EVENT_TYPE_TO_ID.get(req.event_type, 0)], dtype=torch.long, device=device)
    gap = torch.tensor([[float(req.time_gap_hours)]], dtype=torch.float32, device=device)
    feedback = torch.tensor([[float(req.feedback_value)]], dtype=torch.float32, device=device)
    state = snapshot_to_state(req.previous_state, model, device)
    out, new_state = model.step(token_ids, platform_ids, event_type_ids, gap, feedback, state)
    intent_prob = torch.softmax(out["intent_logits"], dim=-1)[0]
    route_prob = torch.softmax(out["router_logits"], dim=-1)[0]
    action_prob = torch.softmax(out["next_action_logits"], dim=-1)[0]
    intent_idx = int(intent_prob.argmax())
    route_idx = int(route_prob.argmax())
    action_idx = int(action_prob.argmax())
    confidence = float((intent_prob.max() + route_prob.max() + action_prob.max()) / 3.0)
    return {
        "intent": INTENTS[intent_idx],
        "selected_agent": AGENTS[route_idx],
        "next_action": NEXT_ACTIONS[action_idx],
        "confidence": confidence,
        "new_state": new_state,
    }
