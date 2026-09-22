from __future__ import annotations
import argparse
import json
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

PLATFORMS = ["web", "zalo", "powerpoint"]

TEMPLATES = {
    "chat": ["xin chào", "giải thích giúp tôi", "nói rõ hơn phần này"],
    "research": ["tìm tài liệu về {topic}", "phân tích {topic}", "nghiên cứu tiếp {topic}"],
    "summarize": ["tóm tắt phần {topic}", "rút gọn nội dung về {topic}", "tổng hợp ý chính {topic}"],
    "presentation_edit": ["làm slide về {topic}", "rút chữ slide {topic}", "biến phần {topic} thành sơ đồ"],
    "recommendation": ["gợi ý nội dung tiếp theo về {topic}", "đề xuất cách làm {topic}", "nên làm gì tiếp với {topic}"],
    "followup": ["làm tiếp phần hôm trước", "tiếp tục công việc đang làm", "mở lại ngữ cảnh trước"],
}
TOPICS = ["DUSN-X", "AI Agent", "machine learning", "dataset", "PowerPoint", "Zalo", "MLOps"]

AGENT_FOR_INTENT = {
    "chat": "conversation",
    "research": "search_rag",
    "summarize": "productivity",
    "presentation_edit": "productivity",
    "recommendation": "conversation",
    "followup": "conversation",
}
ACTION_FOR_INTENT = {
    "chat": "reply",
    "research": "search",
    "summarize": "summarize",
    "presentation_edit": "edit_slide",
    "recommendation": "recommend",
    "followup": "clarify",
}


def choose_intent(platform: str, last_intent: str | None):
    weights = {
        "web": [0.10, 0.30, 0.18, 0.12, 0.18, 0.12],
        "zalo": [0.25, 0.20, 0.16, 0.05, 0.18, 0.16],
        "powerpoint": [0.05, 0.10, 0.20, 0.45, 0.08, 0.12],
    }[platform]
    intents = list(TEMPLATES)
    if last_intent and random.random() < 0.35:
        return last_intent
    return random.choices(intents, weights=weights, k=1)[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", type=int, default=10000)
    ap.add_argument("--users", type=int, default=500)
    ap.add_argument("--out", default="data/synthetic_10k.jsonl")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    random.seed(args.seed)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if args.events < args.users:
        raise ValueError("events must be greater than or equal to users")
    per_user, extra = divmod(args.events, args.users)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)

    with out.open("w", encoding="utf-8") as f:
        for u in range(args.users):
            uid = f"u-{u:06d}"
            current = start + timedelta(hours=random.randint(0, 72))
            last_intent = None
            n = per_user + (1 if u < extra else 0)
            for _ in range(n):
                platform = random.choices(PLATFORMS, weights=[0.45, 0.30, 0.25], k=1)[0]
                intent = choose_intent(platform, last_intent)
                topic = random.choice(TOPICS)
                content = random.choice(TEMPLATES[intent]).format(topic=topic)
                gap = random.expovariate(1/8.0)
                current += timedelta(hours=gap)
                positive = random.random() < 0.82
                feedback = random.uniform(0.2, 1.0) if positive else random.uniform(-1.0, -0.1)
                row = {
                    "event_id": str(uuid.uuid4()),
                    "global_user_id": uid,
                    "platform": platform,
                    "session_id": f"s-{uid}-{current.date().isoformat()}",
                    "event_time_utc": current.isoformat(),
                    "event_type": "message",
                    "content": content,
                    "intent_label": intent,
                    "selected_agent": AGENT_FOR_INTENT[intent],
                    "next_action_label": ACTION_FOR_INTENT[intent],
                    "feedback_value": round(feedback, 4),
                    "task_success": positive,
                    "synthetic": True,
                }
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                last_intent = intent
    print(f"Wrote {args.events} synthetic events to {out}")
    print("IMPORTANT: synthetic data is for pipeline/prototype testing and must be labeled as synthetic in reports.")

if __name__ == "__main__":
    main()
