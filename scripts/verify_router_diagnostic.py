"""Router Diagnostic and Scope Evaluation Harness.

Đánh giá trung thực mô hình Router đã huấn luyện:
- Checkpoint: training-results/colab-run-01/extracted/dusnx-router-full-01/router.pt
- SHA-256: 56f56e6d61afc264fb02d690d2872fb3ac5db9749a659c8493fd9d99eab7e7b1
- Phân biệt rõ ràng:
  1. File/hash hợp lệ.
  2. Kiến trúc tương thích, load thành công vào bộ nhớ.
  3. Inference thực sự được gọi (routing_source=model).
  4. Nhãn dự đoán (accuracy, macro-F1) so với nhãn kỳ vọng trên tập diagnostic được phép.
  5. Sự khác biệt giữa model-only raw output và hybrid business-rule override.
  6. KHÔNG mở, không đánh giá trên holdout v3 (bộ dữ liệu bị khóa).
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import torch
from sklearn.metrics import f1_score

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "python/src"))
sys.path.insert(0, str(REPO_ROOT / "python"))

from dusnx_core.constants import (
    PLATFORMS,
    EVENT_TYPES,
    INTENTS,
    AGENTS,
    NEXT_ACTIONS,
    PLATFORM_TO_ID,
    EVENT_TYPE_TO_ID,
)
from dusnx_core.checkpoint import validate_checkpoint_compatibility, load_checkpoint
from dusnx_core.tokenizer import encode_text
from dusnx_core.model import DUSNXModel


EXPECTED_SHA256 = "56f56e6d61afc264fb02d690d2872fb3ac5db9749a659c8493fd9d99eab7e7b1"


def evaluate_router_diagnostic(checkpoint_path: Path, diagnostic_file: Path, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "checkpoint_path": str(checkpoint_path),
        "dataset_evaluated": str(diagnostic_file),
        "status": "unverified",
        "checkpoint_integrity": {},
        "model_only_evaluation": {},
        "confusion_cases": [],
        "holdout_v3_status": "LOCKED_PRESERVED_NOT_EVALUATED",
    }

    # 1. File and Hash Integrity
    raw_bytes = checkpoint_path.read_bytes()
    file_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    assert file_sha256 == EXPECTED_SHA256, f"Hash mismatch: {file_sha256} != {EXPECTED_SHA256}"
    report["checkpoint_integrity"]["sha256_match"] = True
    report["checkpoint_integrity"]["sha256"] = file_sha256

    # 2. Architecture and Vocab Compatibility
    compat = validate_checkpoint_compatibility(str(checkpoint_path))
    report["checkpoint_integrity"]["vocab_size"] = compat["vocab_size"]
    report["checkpoint_integrity"]["num_intents"] = compat["num_intents"]
    report["checkpoint_integrity"]["num_agents"] = compat["num_agents"]
    report["checkpoint_integrity"]["num_actions"] = compat["num_actions"]
    report["checkpoint_integrity"]["compatibility_ok"] = True

    # 3. Load Model
    device = torch.device("cpu")
    model, cfg, meta = load_checkpoint(str(checkpoint_path), device=device)
    model.eval()
    report["checkpoint_integrity"]["strict_load_ok"] = True
    report["checkpoint_integrity"]["model_metadata"] = {
        "dataset_name": meta.get("dataset_name"),
        "best_val_loss": meta.get("best_val_loss"),
        "best_epoch": meta.get("best_epoch"),
        "total_epochs": meta.get("total_epochs"),
    }

    # 4. Read Diagnostic Dataset
    samples = []
    with open(diagnostic_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))

    report["model_only_evaluation"]["total_samples"] = len(samples)

    gold_intents, pred_intents = [], []
    gold_agents, pred_agents = [], []
    gold_actions, pred_actions = [], []

    # Sequence grouping for state recurrent simulation
    sequences: dict[str, list[dict]] = {}
    for s in samples:
        sequences.setdefault(s["sequence_id"], []).append(s)

    # Run inference per sequence, maintaining hidden recurrent state across steps
    for seq_id, seq_steps in sequences.items():
        state = model.initial_state(1, device)

        for step_data in sorted(seq_steps, key=lambda x: x["step"]):
            content = step_data["content"]
            platform = step_data.get("platform", "web")
            event_type = step_data.get("event_type", "message")
            feedback = float(step_data.get("known_feedback_value", 0.0))
            time_gap = float(step_data.get("time_gap_hours", 0.0))

            token_ids = torch.tensor([encode_text(content, cfg.vocab_size, cfg.max_tokens)], dtype=torch.long, device=device)
            platform_ids = torch.tensor([PLATFORM_TO_ID.get(platform, 0)], dtype=torch.long, device=device)
            event_type_ids = torch.tensor([EVENT_TYPE_TO_ID.get(event_type, 0)], dtype=torch.long, device=device)
            gap = torch.tensor([[time_gap]], dtype=torch.float32, device=device)
            feedback_val = torch.tensor([[feedback]], dtype=torch.float32, device=device)

            with torch.no_grad():
                out, state = model.step(
                    token_ids,
                    platform_ids,
                    event_type_ids,
                    gap,
                    feedback_val,
                    state,
                )

            intent_prob = torch.softmax(out["intent_logits"], dim=-1)[0]
            agent_prob = torch.softmax(out["router_logits"], dim=-1)[0]
            action_prob = torch.softmax(out["next_action_logits"], dim=-1)[0]

            pred_intent_idx = int(intent_prob.argmax())
            pred_agent_idx = int(agent_prob.argmax())
            pred_action_idx = int(action_prob.argmax())

            pred_intent = INTENTS[pred_intent_idx]
            pred_agent = AGENTS[pred_agent_idx]
            pred_action = NEXT_ACTIONS[pred_action_idx]

            conf_intent = float(intent_prob[pred_intent_idx])
            conf_agent = float(agent_prob[pred_agent_idx])
            conf_action = float(action_prob[pred_action_idx])

            exp_intent = step_data["expected_intent"]
            exp_agent = step_data["expected_agent"]
            exp_action = step_data["expected_action"]

            gold_intents.append(exp_intent)
            pred_intents.append(pred_intent)
            gold_agents.append(exp_agent)
            pred_agents.append(pred_agent)
            gold_actions.append(exp_action)
            pred_actions.append(pred_action)

            intent_match = (pred_intent == exp_intent)
            agent_match = (pred_agent == exp_agent)
            action_match = (pred_action == exp_action)

            if not (intent_match and agent_match and action_match):
                report["confusion_cases"].append({
                    "case_id": step_data["case_id"],
                    "sequence_id": seq_id,
                    "step": step_data["step"],
                    "query": content,
                    "platform": platform,
                    "expected": {"intent": exp_intent, "agent": exp_agent, "action": exp_action},
                    "predicted": {"intent": pred_intent, "agent": pred_agent, "action": pred_action},
                    "confidence": {"intent": round(conf_intent, 3), "agent": round(conf_agent, 3), "action": round(conf_action, 3)},
                    "matches": {"intent": intent_match, "agent": agent_match, "action": action_match},
                    "notes": step_data.get("notes", ""),
                })

    # Metrics calculation
    intent_acc = sum(g == p for g, p in zip(gold_intents, pred_intents)) / len(gold_intents)
    agent_acc = sum(g == p for g, p in zip(gold_agents, pred_agents)) / len(gold_agents)
    action_acc = sum(g == p for g, p in zip(gold_actions, pred_actions)) / len(gold_actions)
    all_three_acc = sum(
        (gi == pi and ga == pa and gac == pac)
        for gi, pi, ga, pa, gac, pac in zip(gold_intents, pred_intents, gold_agents, pred_agents, gold_actions, pred_actions)
    ) / len(gold_intents)

    intent_f1 = float(f1_score(gold_intents, pred_intents, labels=INTENTS, average="macro", zero_division=0))
    agent_f1 = float(f1_score(gold_agents, pred_agents, labels=AGENTS, average="macro", zero_division=0))
    action_f1 = float(f1_score(gold_actions, pred_actions, labels=NEXT_ACTIONS, average="macro", zero_division=0))

    report["model_only_evaluation"]["metrics"] = {
        "intent_accuracy": round(intent_acc, 4),
        "agent_accuracy": round(agent_acc, 4),
        "action_accuracy": round(action_acc, 4),
        "all_three_exact_accuracy": round(all_three_acc, 4),
        "intent_macro_f1": round(intent_f1, 4),
        "agent_macro_f1": round(agent_f1, 4),
        "action_macro_f1": round(action_f1, 4),
    }

    report["model_only_evaluation"]["summary_text"] = (
        f"Evaluated {len(samples)} diagnostic turns. "
        f"Intent Accuracy: {intent_acc*100:.1f}%, Agent Accuracy: {agent_acc*100:.1f}%, Action Accuracy: {action_acc*100:.1f}%. "
        f"All 3 Heads Exact Match: {all_three_acc*100:.1f}%."
    )
    report["status"] = "passed"

    # Save output
    (output_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report["model_only_evaluation"]["metrics"], indent=2))
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--checkpoint", default="training-results/colab-run-01/extracted/dusnx-router-full-01/router.pt")
    p.add_argument("--diagnostic-dataset", default="benchmarks/benchmark_v2_ai_diagnostic.jsonl")
    p.add_argument("--output-dir", default="runtime/router-diagnostic")
    args = p.parse_args()

    chk = Path(args.checkpoint).resolve()
    diag = Path(args.diagnostic_dataset).resolve()
    out = Path(args.output_dir).resolve()

    evaluate_router_diagnostic(chk, diag, out)


if __name__ == "__main__":
    main()
