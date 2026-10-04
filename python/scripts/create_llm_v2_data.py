"""Create deterministic AI-draft bilingual development data; never touches v1/holdout."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "datasets" / "llm_sft_v2"
DRAFT_REVISION = "post-week4-v2-draft-03"

TOPICS = {
    "train": {
        "vi": ["PostgreSQL", "Azure", "FastAPI", "Redis", "React", "MinIO", "Kafka", "ONNX", "Flutter", "gRPC"],
        "en": ["SQLite", "GCP", "Django", "Memcached", "Vue", "S3", "RabbitMQ", "TorchServe", "Kotlin", "REST"],
    },
    "validation": {
        "vi": ["lịch họp", "ngân sách", "kênh thông báo", "bố cục báo cáo", "nhà cung cấp", "hạn nộp"],
        "en": ["museum visit", "release date", "print format", "support rota", "delivery window", "project owner"],
    },
    "test": {
        "vi": ["hội thảo", "câu lạc bộ", "chuyến đi", "bản tin", "phòng học", "cuộc thi"],
        "en": ["reading group", "design review", "community event", "research note", "training session", "volunteer shift"],
    },
}
FAMILIES = ["multi_object_clarification", "false_save", "language_policy", "supersede",
            "pending_not_final", "cross_platform", "missing_memory", "lost_response_retry",
            "no_future_fact", "revoked_fact", "user_isolation", "technical_code_switch"]


LEAD_VARIANTS = {
    "vi": [
        "Trong biên bản rà soát buổi sáng, người kiểm thử chỉ dùng dữ kiện đã xác nhận và bỏ qua mọi suy đoán",
        "Sau khi đối chiếu nhật ký thao tác với phiếu bàn giao, nhóm vận hành yêu cầu trả lời dựa đúng trạng thái cuối cùng",
        "Tại cuộc họp nghiệm thu ngắn, thư ký ghi riêng sự kiện hiện hành để tránh lẫn với đề xuất chưa được duyệt",
        "Khi chuyển việc giữa hai ứng dụng, chuyên viên hỗ trợ kiểm tra lại nguồn gốc từng thông tin trước khi phản hồi",
        "Trong lần phục hồi sau sự cố mạng, điều phối viên dùng biên nhận và mốc thời gian thay cho phỏng đoán",
        "Ở phiên làm việc độc lập, người đánh giá tách dữ liệu của từng tài khoản và không sử dụng thông tin ngoài ngữ cảnh",
        "Trước giờ phát hành, nhóm chất lượng yêu cầu câu trả lời ngắn nhưng phải phân biệt rõ dữ kiện cũ, mới và đang chờ",
        "Trong ca trực cuối ngày, kỹ sư chỉ công nhận thay đổi có xác nhận và phải hỏi lại nếu đối tượng chưa rõ",
        "Khi tổng hợp hồ sơ cho báo cáo, trợ lý phải giữ nguyên ngôn ngữ được yêu cầu và không tuyên bố lưu thành công sai",
    ],
    "en": [
        "During a morning audit, the checker uses only confirmed evidence and excludes every unsupported assumption",
        "After matching the operation log with the handoff receipt, the support team answers from the final recorded state",
        "In a short acceptance meeting, the recorder separates the active event from every proposal still awaiting approval",
        "While work moves between two applications, the operator verifies the provenance of each detail before responding",
        "During recovery from a network interruption, the coordinator relies on receipts and timestamps rather than guesses",
        "In an isolated work session, the reviewer keeps accounts separate and never imports facts from outside the context",
        "Before release, quality staff require a concise answer that distinguishes old, current, and pending information",
        "On the final support shift, the engineer accepts only confirmed changes and asks when the referenced object is unclear",
        "When assembling the report record, the assistant follows the requested language and never invents a successful save",
    ],
}


def scenario(family: str, topic: str, marker: str, language: str, split: str, variant: int) -> tuple[str, str, str, list[str], list[str]]:
    """Return a semantically matched draft; split wording stays intentionally distinct."""
    vi = language == "vi"
    split_lead = ({
        "train": "Bản ghi luyện tập từ nhật ký thiết kế nội bộ",
        "validation": "Phiếu xác minh trước phát hành dành cho người kiểm tra",
        "test": "Tình huống độc lập do nhóm nghiệm thu ghi nhận",
    }[split] if vi else {
        "train": "A training note extracted from an internal design log",
        "validation": "A pre-release verification card prepared for the checker",
        "test": "An independent scenario recorded by the acceptance team",
    }[split])
    diversity_lead = LEAD_VARIANTS[language][variant % len(LEAD_VARIANTS[language])]
    lead = f"{split_lead}. {diversity_lead}"
    if family == "multi_object_clarification":
        user = (f"{lead} {marker}: có hai mục cùng loại, {topic} A chốt lúc 09:00 và {topic} B chốt lúc 15:30. Hạn của mục này là mấy giờ?"
                if vi else f"{lead} {marker}: two separate items exist; {topic} A closes at 09:00 and {topic} B at 15:30. What time does this one close?")
        answer = (f"Bạn đang hỏi {topic} A hay {topic} B?" if vi else f"Which item do you mean, {topic} A or {topic} B?")
        return user, answer, "clarify", [], []
    if family == "false_save":
        user = (f"{lead} {marker}: yêu cầu lưu ghi chú về {topic} báo lỗi kết nối, chưa có biên nhận và giao diện không hề báo đã lưu thành công. Ghi chú đã được lưu chưa?"
                if vi else f"{lead} {marker}: saving the {topic} note failed with a connection error, no receipt exists, and the UI did not say saved successfully. Is it saved?")
        answer = ("Tôi chưa thể xác nhận đã lưu vì yêu cầu bị lỗi kết nối. Bạn muốn thử lại không?" if vi
                  else "I cannot confirm that it is saved because the request failed. Would you like to retry?")
        return user, answer, "clarify", [], ["đã lưu thành công" if vi else "saved successfully"]
    if family == "language_policy":
        user = (f"{lead} {marker}: tôi đang hỏi về {topic}, nhưng từ giờ hãy trả lời bằng tiếng Anh. What is the active choice?" if vi
                else f"{lead} {marker}: I am asking about {topic}, but please answer in Vietnamese from now on. Lựa chọn nào đang hiệu lực?")
        answer = ("I will answer in English as requested; no confirmed choice is available in this prompt." if vi
                  else "Tôi sẽ trả lời bằng tiếng Việt theo yêu cầu; câu này chưa cung cấp lựa chọn đã xác nhận.")
        return user, answer, "answer", [], []
    if family == "supersede":
        old, new = (f"{topic} bản cũ", f"{topic} bản mới") if vi else (f"old {topic}", f"new {topic}")
        user = (f"{lead} {marker}: quyết định {old} đã được thay thế và xác nhận bằng {new}. Hiện dùng phương án nào?" if vi
                else f"{lead} {marker}: the decision {old} was replaced and confirmed as {new}. Which option is active now?")
        answer = (f"Phương án đang hiệu lực là {new}." if vi else f"The active option is {new}.")
        return user, answer, "answer", [new], [old]
    if family == "pending_not_final":
        current, proposal = (f"{topic} hiện hành", f"đề xuất {topic} thay thế") if vi else (f"current {topic}", f"proposed replacement for {topic}")
        user = (f"{lead} {marker}: {current} đã xác nhận; {proposal} mới được nêu và chưa duyệt. Điều gì đang có hiệu lực?" if vi
                else f"{lead} {marker}: {current} is confirmed; the {proposal} is pending approval. What is active?")
        answer = (f"{current} vẫn có hiệu lực; đề xuất mới chưa được duyệt." if vi else f"The {current} remains active; the proposal is not approved.")
        return user, answer, "answer", [current], []
    if family == "cross_platform":
        old, new = ("thứ Ba", "thứ Năm") if vi else ("Tuesday", "Thursday")
        user = (f"{lead} {marker}: trên Web lịch {topic} là {old}; sau đó PowerPoint ghi thay đổi đã xác nhận sang {new}. Khi quay lại Web, lịch là ngày nào?" if vi
                else f"{lead} {marker}: Web showed {topic} on {old}; PowerPoint later recorded a confirmed move to {new}. What day should Web show now?")
        answer = (f"Lịch {topic} hiện là {new}." if vi else f"The current {topic} schedule is {new}.")
        return user, answer, "answer", [new], [old]
    if family == "missing_memory":
        user = (f"{lead} {marker}: hồ sơ chỉ ghi tên {topic}, không ghi người phụ trách. Ai đang phụ trách?" if vi
                else f"{lead} {marker}: the record only names {topic}; no owner is recorded. Who is responsible?")
        answer = (f"Tôi chưa có thông tin người phụ trách {topic}. Bạn có thể cho tôi biết tên người đó không?" if vi
                  else f"I do not have an owner recorded for {topic}. Can you tell me who is responsible?")
        return user, answer, "clarify", [topic], []
    if family == "lost_response_retry":
        user = (f"{lead} {marker}: biên nhận xác nhận lựa chọn {topic} đã lưu, nhưng phản hồi mạng bị mất. Có cần tạo lại bản ghi không?" if vi
                else f"{lead} {marker}: a receipt confirms that {topic} was saved, but the network response was lost. Should another record be created?")
        answer = (f"Không cần tạo bản ghi mới; biên nhận cho thấy {topic} đã được lưu. Có thể trả lại kết quả cũ." if vi
                  else f"No new record is needed; the receipt shows that {topic} was saved. The prior result can be replayed.")
        return user, answer, "answer", [topic], []
    if family == "no_future_fact":
        user = (f"{lead} {marker}: hiện chỉ xác nhận {topic}; kế hoạch tháng sau chưa được quyết định. Hãy nêu trạng thái hiện tại." if vi
                else f"{lead} {marker}: only {topic} is confirmed now; next month's plan is undecided. State the current status.")
        answer = (f"Hiện tại chỉ có {topic} được xác nhận." if vi else f"Only {topic} is confirmed at present.")
        return user, answer, "answer", [topic], ["kế hoạch tháng sau" if vi else "next month's plan"]
    if family == "revoked_fact":
        old = f"ưu tiên {topic}" if vi else f"preference for {topic}"
        user = (f"{lead} {marker}: người dùng đã thu hồi {old} và chưa đặt lựa chọn mới. Tôi nên áp dụng ưu tiên nào?" if vi
                else f"{lead} {marker}: the user revoked the {old} and set no replacement. Which preference should be applied?")
        answer = ("Hiện không có ưu tiên nào đang hiệu lực." if vi else "There is no active preference for your account.")
        return user, answer, "answer", [], [old]
    if family == "user_isolation":
        user = (f"{lead} {marker}: tài khoản khác có quyết định về {topic}, còn tài khoản hiện tại không có bản ghi. Quyết định của tôi là gì?" if vi
                else f"{lead} {marker}: another account has a decision about {topic}, while this account has no record. What is my decision?")
        answer = (f"Tài khoản hiện tại chưa có quyết định về {topic}. Bạn muốn lưu lựa chọn nào?" if vi
                  else f"This account has no decision about {topic}. Which choice would you like to save?")
        return user, answer, "clarify", [topic], []
    # technical_code_switch
    user = (f"{lead} {marker}: API cho {topic} trả timeout, nhưng hãy giải thích ngắn gọn bằng tiếng Việt và không báo thao tác thành công." if vi
            else f"{lead} {marker}: the {topic} API returned a timeout; please explain briefly in English without claiming success.")
    answer = (f"API của {topic} đã hết thời gian chờ nên chưa thể xác nhận thao tác thành công." if vi
              else f"The {topic} API is unavailable after the timeout, so the operation cannot be confirmed as successful.")
    return user, answer, "answer", [topic], []


def row(split: str, index: int, language: str) -> dict:
    topic_list = TOPICS[split][language]
    topic = topic_list[index % len(topic_list)]
    base_family = FAMILIES[index % len(FAMILIES)]
    family = f"{split}_{base_family}"
    marker = f"{split.upper()}-{index:03d}"
    # Offset each split so the same family/index never reuses the same narrative
    # frame across train, validation, and the AI-only test draft.
    variant = index // len(FAMILIES) + {"train": 0, "validation": 3, "test": 6}[split]
    user, answer, mode, required, forbidden = scenario(base_family, topic, marker, language, split, variant)
    response_language = ({"vi": "en", "en": "vi"}[language]
                         if base_family == "language_policy" else language)
    return {
        "id": f"llmv2-{split}-{index:03d}", "source": "synthetic_designed",
        "source_revision": DRAFT_REVISION, "license": "CC0-1.0",
        "generation_method": "AI-generated", "scenario_family": family,
        "sequence_id": f"llmv2-seq-{split}-{index:03d}", "user_id": f"fictional-v2-{split}-{index:03d}",
        "split": split, "review_status": "needs_human_review", "data_kind": "designed_conversation",
        "messages": [{"role": "system", "content": "DUSN-X bilingual development scenario. Use only confirmed facts."},
                     {"role": "user", "content": user}, {"role": "assistant", "content": answer}],
        "quality_contracts": [{"assistant_turn": 1, "response_mode": mode,
            "language": response_language, "response_language": response_language,
            "required_facts": required, "forbidden_facts": forbidden, "future_facts": [],
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
                "locked": False, "source_revision": DRAFT_REVISION, "files": files,
                "counts": {name: {"sequences": len(rows), "assistant_pairs": len(rows)} for name, rows in sets.items()},
                "training_allowed": False, "official_evaluation_allowed": False}
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    provenance = {"source": "AI-generated", "review_status": "needs_human_review", "license": "CC0-1.0",
                  "contains_real_pii": False, "derived_from_locked_test_v1": False,
                  "holdout_v3_accessed_for_generation": False}
    (OUT / "provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
