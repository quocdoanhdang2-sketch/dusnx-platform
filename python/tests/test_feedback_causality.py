from pathlib import Path

import pytest

from dusnx_core.dataset import SequenceWindowDataset
from scripts.train import build_training_metadata


class TinyConfig:
    max_tokens = 4
    vocab_size = 128


def event(user, hour, feedback="missing"):
    row = {
        "global_user_id": user,
        "platform": "web",
        "content": f"event-{user}-{hour}",
        "event_type": "message",
        "event_time_utc": f"2026-01-01T{hour:02d}:00:00Z",
        "intent_label": "chat",
        "selected_agent": "conversation",
        "next_action_label": "reply",
    }
    if feedback != "missing":
        row["feedback_value"] = feedback
    return row


def valid_feedback(sample):
    mask = sample["valid_mask"].squeeze(-1).bool()
    return sample["feedback"].squeeze(-1)[mask].tolist()


def test_feedback_is_shifted_by_one_event_for_the_same_user():
    dataset = SequenceWindowDataset(
        [event("u1", 1, 0.25), event("u1", 2, -0.5), event("u1", 3, 0.75)],
        TinyConfig(),
        sequence_len=3,
        stride=3,
    )

    assert valid_feedback(dataset[-1]) == pytest.approx([0.0, 0.25, -0.5])


def test_mid_history_window_uses_feedback_before_the_window():
    dataset = SequenceWindowDataset(
        [
            event("u1", 1, 0.1),
            event("u1", 2, 0.2),
            event("u1", 3, 0.3),
            event("u1", 4, 0.4),
        ],
        TinyConfig(),
        sequence_len=2,
        stride=2,
    )

    assert valid_feedback(dataset[1]) == pytest.approx([0.2, 0.3])


def test_feedback_does_not_cross_users_and_missing_is_neutral():
    dataset = SequenceWindowDataset(
        [
            event("u1", 1, 0.9),
            event("u1", 2, "missing"),
            event("u2", 1, -0.8),
            event("u2", 2, 0.6),
        ],
        TinyConfig(),
        sequence_len=2,
        stride=2,
    )

    assert valid_feedback(dataset[0]) == pytest.approx([0.0, 0.9])
    assert valid_feedback(dataset[1]) == pytest.approx([0.0, -0.8])


def test_training_metadata_records_causal_feedback_and_dataset_provenance():
    dataset_path = Path(__file__).parent / "fixtures" / "benchmark_v1_fixture.jsonl"
    metadata = build_training_metadata(dataset_path, "configs/smoke_v2.yaml", seed=42)

    assert metadata["feedback_contract"] == "previous_event_feedback_v1"
    assert metadata["dataset_sha256"] == "b9d7ea6451526fe0b13912abc4256f957d5bc01883e4c1d46aeac5473f8bc06d"
    assert metadata["data"] == str(dataset_path)
    assert metadata["config"] == "configs/smoke_v2.yaml"
    assert metadata["seed"] == 42
    assert metadata["trained_at_utc"].endswith("Z")
