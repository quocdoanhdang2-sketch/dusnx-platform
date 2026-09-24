from __future__ import annotations
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import torch
from torch.utils.data import Dataset

from .constants import PLATFORM_TO_ID, EVENT_TYPE_TO_ID, INTENT_TO_ID, AGENT_TO_ID, NEXT_ACTION_TO_ID
from .tokenizer import encode_text


def read_jsonl(path: str | Path) -> list[dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def group_sorted(rows: list[dict]) -> dict[str, list[dict]]:
    users = defaultdict(list)
    for r in rows:
        users[r["global_user_id"]].append(r)
    for uid in users:
        users[uid].sort(key=lambda x: x["event_time_utc"])
    return dict(users)


def split_users(users: list[str], seed: int = 42, train=0.8, val=0.1):
    g = torch.Generator().manual_seed(seed)
    perm = torch.randperm(len(users), generator=g).tolist()
    users = [users[i] for i in perm]
    n = len(users)
    n_train = int(n * train)
    n_val = int(n * val)
    return users[:n_train], users[n_train:n_train+n_val], users[n_train+n_val:]


class SequenceWindowDataset(Dataset):
    def __init__(self, rows: list[dict], cfg, sequence_len: int = 12, stride: int = 4, allowed_users: set[str] | None = None):
        self.cfg = cfg
        self.sequence_len = sequence_len
        # Each sample retains the feedback known immediately before its first
        # event.  feedback_value in JSONL is produced *after* an event, so it
        # must only be supplied to the following event for the same user.
        self.samples: list[tuple[list[dict], float]] = []
        grouped = group_sorted(rows)
        for uid, events in grouped.items():
            if allowed_users is not None and uid not in allowed_users:
                continue
            if len(events) < 2:
                continue
            for end in range(2, len(events) + 1, stride):
                start = max(0, end - sequence_len)
                previous_feedback = self._feedback_after(events[start - 1]) if start else 0.0
                self.samples.append((events[start:end], previous_feedback))
            if self.samples and self.samples[-1][0][-1] is not events[-1]:
                start = max(0, len(events) - sequence_len)
                previous_feedback = self._feedback_after(events[start - 1]) if start else 0.0
                self.samples.append((events[start:], previous_feedback))

    @staticmethod
    def _feedback_after(event: dict) -> float:
        """Return feedback emitted after an event; absent feedback means neutral."""
        return float(event.get("feedback_value", 0.0) or 0.0)

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        events, previous_feedback = self.samples[idx]
        L = self.sequence_len
        max_tokens = self.cfg.max_tokens

        token_ids = torch.zeros(L, max_tokens, dtype=torch.long)
        platform_ids = torch.zeros(L, dtype=torch.long)
        event_type_ids = torch.zeros(L, dtype=torch.long)
        time_gap = torch.zeros(L, 1, dtype=torch.float32)
        feedback = torch.zeros(L, 1, dtype=torch.float32)
        valid_mask = torch.zeros(L, 1, dtype=torch.float32)

        offset = L - len(events)
        prev_time = None
        for i, e in enumerate(events):
            j = offset + i
            token_ids[j] = torch.tensor(encode_text(e.get("content", ""), self.cfg.vocab_size, max_tokens))
            platform_ids[j] = PLATFORM_TO_ID[e["platform"]]
            event_type_ids[j] = EVENT_TYPE_TO_ID.get(e.get("event_type", "message"), 0)
            t = datetime.fromisoformat(e["event_time_utc"].replace("Z", "+00:00"))
            if prev_time is None:
                gap = float(e.get("time_gap_hours", 0.0))
            else:
                gap = max(0.0, (t - prev_time).total_seconds() / 3600.0)
            prev_time = t
            time_gap[j, 0] = gap
            # This is feedback available before event e, never its own
            # post-event feedback.  Carrying previous_feedback into a window
            # also makes a window starting mid-history causal.
            feedback[j, 0] = previous_feedback
            previous_feedback = self._feedback_after(e)
            valid_mask[j, 0] = 1.0

        target = events[-1]
        return {
            "token_ids": token_ids,
            "platform_ids": platform_ids,
            "event_type_ids": event_type_ids,
            "time_gap": time_gap,
            "feedback": feedback,
            "valid_mask": valid_mask,
            "intent": torch.tensor(INTENT_TO_ID[target["intent_label"]], dtype=torch.long),
            "agent": torch.tensor(AGENT_TO_ID[target["selected_agent"]], dtype=torch.long),
            "next_action": torch.tensor(NEXT_ACTION_TO_ID[target["next_action_label"]], dtype=torch.long),
        }
