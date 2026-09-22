from __future__ import annotations
import math
from dataclasses import dataclass

import torch
from torch import nn

from .config import ModelConfig
from .constants import PLATFORMS, EVENT_TYPES, INTENTS, AGENTS, NEXT_ACTIONS


@dataclass
class DusnxState:
    global_state: torch.Tensor       # [B, G]
    platform_states: torch.Tensor    # [B, P, S]
    task_state: torch.Tensor         # [B, T]


class TimeAwareStateCell(nn.Module):
    def __init__(self, input_dim: int, state_dim: int):
        super().__init__()
        self.state_dim = state_dim
        self.candidate = nn.Linear(input_dim + state_dim, state_dim)
        self.gate = nn.Linear(input_dim + state_dim + 1, state_dim)
        self.decay_rate = nn.Parameter(torch.zeros(state_dim))

    def forward(self, prev: torch.Tensor, x: torch.Tensor, delta_hours: torch.Tensor) -> torch.Tensor:
        # delta_hours: [B, 1]
        delta = torch.log1p(delta_hours.clamp_min(0.0))
        rate = torch.nn.functional.softplus(self.decay_rate).unsqueeze(0)
        decay = torch.exp(-rate * delta)
        decayed_prev = prev * decay
        candidate = torch.tanh(self.candidate(torch.cat([decayed_prev, x], dim=-1)))
        gate = torch.sigmoid(self.gate(torch.cat([decayed_prev, x, delta], dim=-1)))
        return gate * candidate + (1.0 - gate) * decayed_prev


class EventEncoder(nn.Module):
    def __init__(self, cfg: ModelConfig):
        super().__init__()
        self.cfg = cfg
        self.token_emb = nn.Embedding(cfg.vocab_size, cfg.token_dim, padding_idx=0)
        self.platform_emb = nn.Embedding(len(PLATFORMS), cfg.platform_dim)
        self.event_type_emb = nn.Embedding(len(EVENT_TYPES), cfg.event_type_dim)
        in_dim = cfg.token_dim + cfg.platform_dim + cfg.event_type_dim + 2
        self.proj = nn.Sequential(
            nn.Linear(in_dim, cfg.event_hidden),
            nn.ReLU(),
            nn.Dropout(cfg.dropout),
            nn.Linear(cfg.event_hidden, cfg.event_hidden),
            nn.ReLU(),
        )

    def forward(self, token_ids, platform_ids, event_type_ids, time_gap_hours, feedback):
        # token_ids [B, T]
        emb = self.token_emb(token_ids)  # [B,T,D]
        mask = (token_ids != 0).float().unsqueeze(-1)
        denom = mask.sum(dim=1).clamp_min(1.0)
        text_vec = (emb * mask).sum(dim=1) / denom
        p = self.platform_emb(platform_ids)
        e = self.event_type_emb(event_type_ids)
        numeric = torch.cat([torch.log1p(time_gap_hours.clamp_min(0.0)), feedback], dim=-1)
        return self.proj(torch.cat([text_vec, p, e, numeric], dim=-1))


class DUSNXModel(nn.Module):
    def __init__(self, cfg: ModelConfig):
        super().__init__()
        self.cfg = cfg
        self.encoder = EventEncoder(cfg)
        self.global_cell = TimeAwareStateCell(cfg.event_hidden, cfg.global_state_dim)
        self.platform_cell = TimeAwareStateCell(cfg.event_hidden, cfg.platform_state_dim)
        self.task_cell = TimeAwareStateCell(cfg.event_hidden, cfg.task_state_dim)

        combined = cfg.global_state_dim + cfg.platform_state_dim + cfg.task_state_dim
        self.shared = nn.Sequential(
            nn.Linear(combined, combined),
            nn.ReLU(),
            nn.Dropout(cfg.dropout),
        )
        self.intent_head = nn.Linear(combined, len(INTENTS))
        self.router_head = nn.Linear(combined, len(AGENTS))
        self.next_action_head = nn.Linear(combined, len(NEXT_ACTIONS))
        self.confidence_head = nn.Linear(combined, 1)

    def initial_state(self, batch_size: int, device=None) -> DusnxState:
        device = device or next(self.parameters()).device
        return DusnxState(
            global_state=torch.zeros(batch_size, self.cfg.global_state_dim, device=device),
            platform_states=torch.zeros(batch_size, len(PLATFORMS), self.cfg.platform_state_dim, device=device),
            task_state=torch.zeros(batch_size, self.cfg.task_state_dim, device=device),
        )

    def step(self, token_ids, platform_ids, event_type_ids, time_gap_hours, feedback, state: DusnxState):
        x = self.encoder(token_ids, platform_ids, event_type_ids, time_gap_hours, feedback)
        new_global = self.global_cell(state.global_state, x, time_gap_hours)

        # Select and update only the active platform state for each item in the batch.
        batch_idx = torch.arange(platform_ids.shape[0], device=platform_ids.device)
        current_platform_state = state.platform_states[batch_idx, platform_ids]
        updated_platform_state = self.platform_cell(current_platform_state, x, time_gap_hours)
        new_platform_states = state.platform_states.clone()
        new_platform_states[batch_idx, platform_ids] = updated_platform_state

        new_task = self.task_cell(state.task_state, x, time_gap_hours)
        active_platform = new_platform_states[batch_idx, platform_ids]
        combined = torch.cat([new_global, active_platform, new_task], dim=-1)
        h = self.shared(combined)
        out = {
            "intent_logits": self.intent_head(h),
            "router_logits": self.router_head(h),
            "next_action_logits": self.next_action_head(h),
            "confidence": torch.sigmoid(self.confidence_head(h)).squeeze(-1),
        }
        return out, DusnxState(new_global, new_platform_states, new_task)

    def forward(self, token_ids, platform_ids, event_type_ids, time_gap_hours, feedback, valid_mask=None):
        # Inputs: [B, L, ...]
        B, L, T = token_ids.shape
        state = self.initial_state(B, token_ids.device)
        last_out = None
        for t in range(L):
            prev = state
            candidate_out, candidate_state = self.step(
                token_ids[:, t],
                platform_ids[:, t],
                event_type_ids[:, t],
                time_gap_hours[:, t],
                feedback[:, t],
                state,
            )
            if valid_mask is not None:
                m = valid_mask[:, t].view(B, 1)
                mp = m.view(B, 1, 1)
                state = DusnxState(
                    global_state=m * candidate_state.global_state + (1.0 - m) * prev.global_state,
                    platform_states=mp * candidate_state.platform_states + (1.0 - mp) * prev.platform_states,
                    task_state=m * candidate_state.task_state + (1.0 - m) * prev.task_state,
                )
            else:
                state = candidate_state
            last_out = candidate_out
        return last_out, state
