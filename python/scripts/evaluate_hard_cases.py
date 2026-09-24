from __future__ import annotations

import argparse
import json

import torch

from dusnx_core.checkpoint import load_checkpoint, model_identifier
from dusnx_core.inference import process_one
from dusnx_core.routing_policy import match_explicit_route
from dusnx_core.schema import ProcessRequest


CASES = [
    ("web", "Tóm tắt nội dung AI Agent tôi đang nghiên cứu", "summarize"),
    ("web", "Rút gọn kết quả tìm kiếm về DUSN-X thành các ý chính", "summarize"),
    ("powerpoint", "Tạo 5 slide từ chủ đề AI Agent tôi vừa nghiên cứu", "presentation_edit"),
    ("powerpoint", "Chuyển kết quả tìm kiếm trước đó thành bài trình chiếu", "presentation_edit"),
    ("web", "Tìm bài báo về Multi-Agent rồi phân tích ưu nhược điểm", "research"),
    ("zalo", "Gợi ý ba bước tiếp theo sau khi nghiên cứu DUSN-X", "recommendation"),
    ("zalo", "Tiếp tục phần AI Agent tôi vừa làm trên Web", "followup"),
    ("web", "Xin chào, giải thích DUSN-X giúp tôi", "chat"),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", default="artifacts/dusnx_smoke_v2.pt")
    parser.add_argument("--device", choices=["cpu", "cuda", "auto"], default="auto")
    args = parser.parse_args()

    device = "cuda" if args.device != "cpu" and torch.cuda.is_available() else "cpu"
    model, cfg, metadata = load_checkpoint(args.checkpoint, device)
    model.eval()
    model_version = model_identifier(args.checkpoint, cfg, "trained_dusnx")

    model_correct = 0
    final_correct = 0
    rows = []
    for index, (platform, content, expected) in enumerate(CASES, start=1):
        request = ProcessRequest(
            global_user_id=f"hard-case-{index}",
            platform=platform,
            content=content,
            event_type="message",
        )
        result = process_one(model, cfg, request, model_version, device)
        model_intent = result["intent"]
        model_correct += int(model_intent == expected)

        explicit = match_explicit_route(platform, content)
        final_intent = explicit.intent if explicit is not None else model_intent
        source = "business_rule_override" if explicit is not None and explicit.intent != model_intent else "model"
        final_correct += int(final_intent == expected)
        rows.append({
            "platform": platform,
            "content": content,
            "expected": expected,
            "model": model_intent,
            "final": final_intent,
            "source": source,
            "pass": final_intent == expected,
        })

    report = {
        "checkpoint": args.checkpoint,
        "metadata": metadata,
        "model_version": model_version,
        "device": device,
        "cases": len(CASES),
        "model_accuracy": model_correct / len(CASES),
        "final_routing_accuracy": final_correct / len(CASES),
        "results": rows,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
