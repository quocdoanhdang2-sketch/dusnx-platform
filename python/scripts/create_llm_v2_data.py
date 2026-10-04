"""Create deterministic AI-draft bilingual development data; never touches v1/holdout."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "datasets" / "llm_sft_v2"

VI_TOPICS = ["PostgreSQL", "Azure", "FastAPI", "Redis", "React", "MinIO", "Kafka", "ONNX", "Flutter", "gRPC"]
EN_TOPICS = ["SQLite", "GCP", "Django", "Memcached", "Vue", "S3", "RabbitMQ", "TorchServe", "Kotlin", "REST"]
FAMILIES = ["multi_object_clarification", "false_save", "language_policy", "supersede",
            "pending_not_final", "cross_platform", "missing_memory", "lost_response_retry",
            "no_future_fact", "revoked_fact", "user_isolation", "technical_code_switch"]


def row(split: str, index: int, language: str) -> dict:
    topic = (VI_TOPICS if language == "vi" else EN_TOPICS)[index % 10]
    family = f"{split}_{FAMILIES[index % len(FAMILIES)]}"
    marker = f"{split.upper()}-{index:03d}-{topic}"
    if language == "vi":
        user = f"Trong tình huống {marker}, quyết định hiện tại về {topic} là gì? Nếu chưa có dữ kiện thì nói rõ."
        answer = f"Tôi chưa có quyết định đã xác nhận về {topic} trong tình huống {marker}. Bạn muốn lưu lựa chọn nào?"
    else:
        user = f"In scenario {marker}, what is the current decision about {topic}? Say clearly if no fact is saved."
        answer = f"There is no confirmed decision about {topic} in scenario {marker}. Which choice would you like to save?"
    return {
        "id": f"llmv2-{split}-{index:03d}", "source": "synthetic_designed",
        "source_revision": "post-week4-v2-draft-01", "license": "CC0-1.0",
        "generation_method": "AI-generated", "scenario_family": family,
        "sequence_id": f"llmv2-seq-{split}-{index:03d}", "user_id": f"fictional-v2-{split}-{index:03d}",
        "split": split, "review_status": "needs_human_review", "data_kind": "designed_conversation",
        "messages": [{"role": "system", "content": "DUSN-X bilingual development scenario. Use only confirmed facts."},
                     {"role": "user", "content": user}, {"role": "assistant", "content": answer}],
        "quality_contracts": [{"assistant_turn": 1, "response_mode": "clarify",
            "language": language, "response_language": language,
            "required_facts": [], "forbidden_facts": [], "future_facts": [],
            "criteria": ["grounded", "clarification", "no_false_save", "language_compliance"]}],
    }


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n" for value in rows), encoding="utf-8", newline="\n")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sets = {"train": [row("train", i, "vi" if i % 2 == 0 else "en") for i in range(100)],
            "validation": [row("validation", i, "vi" if i % 2 == 0 else "en") for i in range(24)],
            "test_draft": [row("test", i, "vi" if i % 2 == 0 else "en") for i in range(16)]}
    for name, rows in sets.items():
        write_jsonl(OUT / f"{name}.jsonl", rows)
    files = {f"{name}.jsonl": digest(OUT / f"{name}.jsonl") for name in sets}
    manifest = {"schema_version": 1, "status": "ai_draft_needs_independent_human_review",
                "locked": False, "source_revision": "post-week4-v2-draft-01", "files": files,
                "counts": {name: {"sequences": len(rows), "assistant_pairs": len(rows)} for name, rows in sets.items()},
                "training_allowed": False, "official_evaluation_allowed": False}
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    provenance = {"source": "AI-generated", "review_status": "needs_human_review", "license": "CC0-1.0",
                  "contains_real_pii": False, "derived_from_locked_test_v1": False,
                  "holdout_v3_accessed_for_generation": False}
    (OUT / "provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
