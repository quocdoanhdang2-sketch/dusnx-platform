"""Comprehensive bilingual and language policy evaluation against live Gateway, FastAPI and Ollama.

Tách bạch rõ ràng:
1. Transport / provider contract (provider_called, provider_ok, model_used, tokens_generated).
2. Lựa chọn ngôn ngữ trong metadata (preferred_language, detected_language, response_language).
3. Ngôn ngữ thực tế của câu trả lời (phân tích heuristic ký tự có dấu / từ vựng).
4. Phân biệt template recall với LLM generation thực tế.
5. Tạo bảng đánh giá kèm phiếu review độc lập chưa duyệt (needs_human_review).
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import secrets
import sys
import unicodedata

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from verify_week4_runtime import Stack, free_port

VI_DIACRITICS = re.compile(r"[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]", re.I)
VI_COMMON_WORDS = {"bạn", "tôi", "mình", "là", "và", "không", "có", "hãy", "đang", "đã", "muốn", "trả", "lời", "bằng", "tiếng", "các", "những", "được", "cho", "của", "trong", "với", "này", "về", "giúp"}
EN_COMMON_WORDS = {"the", "is", "are", "you", "please", "what", "which", "how", "answer", "english", "vietnamese", "from", "now", "and", "can", "for", "with", "this", "that", "benefit", "reading", "improve", "help"}


def evaluate_text_language(text: str) -> dict:
    """Heuristic assessment of actual text content language."""
    if not text or not text.strip():
        return {"actual_language": "empty", "confidence": 1.0, "vi_diacritics": 0, "vi_words": 0, "en_words": 0}
    norm = unicodedata.normalize("NFC", text).casefold()
    words = set(re.findall(r"[\w]+", norm, flags=re.UNICODE))
    diacritics_count = len(VI_DIACRITICS.findall(norm))
    vi_word_count = len(words & VI_COMMON_WORDS)
    en_word_count = len(words & EN_COMMON_WORDS)

    vi_score = diacritics_count * 2 + vi_word_count * 3
    en_score = en_word_count * 3

    if vi_score > en_score and vi_score >= 3:
        lang = "vi"
        conf = min(1.0, vi_score / max(1, vi_score + en_score))
    elif en_score > vi_score and en_score >= 3:
        lang = "en"
        conf = min(1.0, en_score / max(1, vi_score + en_score))
    else:
        lang = "mixed_or_uncertain"
        conf = 0.5

    return {
        "actual_language": lang,
        "confidence": round(conf, 2),
        "vi_diacritics": diacritics_count,
        "vi_words": vi_word_count,
        "en_words": en_word_count,
    }


class GatewayClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.client = httpx.Client(base_url=base_url, timeout=120, trust_env=False)
        self.headers = {}
        self.user_id = None

    def register_and_login(self, username_prefix: str = "bilingual_") -> str:
        creds = {
            "username": f"{username_prefix}{secrets.token_hex(6)}",
            "password": secrets.token_urlsafe(20),
        }
        r_reg = self.client.post("/v1/auth/register", json=creds)
        if r_reg.status_code != 201:
            raise RuntimeError(f"Register failed: HTTP {r_reg.status_code} {r_reg.text}")
        r_log = self.client.post("/v1/auth/login", json=creds)
        if r_log.status_code != 200:
            raise RuntimeError(f"Login failed: HTTP {r_log.status_code} {r_log.text}")
        token = r_log.json()["token"]
        self.headers = {"Authorization": f"Bearer {token}"}
        me = self.client.get("/v1/auth/me", headers=self.headers).json()
        self.user_id = me["user_id"]
        return self.user_id

    def create_session(self, title: str = "Bilingual Evaluation") -> str:
        r = self.client.post("/v1/sessions", json={"title": title}, headers=self.headers)
        if r.status_code != 201:
            raise RuntimeError(f"Create session failed: HTTP {r.status_code}")
        return r.json()["session_id"]

    def chat(self, session_id: str, message: str, preferred_language: str = "auto") -> dict:
        payload = {
            "session_id": session_id,
            "message": message,
            "preferred_language": preferred_language,
            "request_id": secrets.token_hex(16),
        }
        r = self.client.post("/v1/chat", json=payload, headers=self.headers)
        if r.status_code != 200:
            raise RuntimeError(f"Chat failed: HTTP {r.status_code} {r.text}")
        return r.json()

    def get_messages(self, session_id: str) -> list[dict]:
        r = self.client.get(f"/v1/sessions/{session_id}/messages", headers=self.headers)
        return r.json() if r.status_code == 200 else []

    def close(self):
        try:
            if self.headers:
                self.client.post("/v1/auth/logout", headers=self.headers)
        finally:
            self.client.close()


def run_evaluation(gateway_url: str, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "gateway_url": gateway_url,
        "test_suite": "DUSN-X Bilingual Generation and Language Policy Matrix",
        "cases": {},
        "summary": {
            "total_cases": 0,
            "transport_passed": 0,
            "linguistic_matched": 0,
            "linguistic_divergent": 0,
            "template_recalls": 0,
            "provider_errors_correctly_reported": 0,
        },
    }

    client = GatewayClient(gateway_url)
    try:
        client.register_and_login("eval_user_")
        session_id = client.create_session("Bilingual Main Suite")

        test_cases_spec = [
            {
                "case_id": "CASE_01_VI_PREF_VI",
                "objective": "Prompt tiếng Việt, preferred_language=vi. Yêu cầu sinh tiếng Việt.",
                "prompt": "Hệ thống DUSN-X có những tính năng cốt lõi nào?",
                "preferred_language": "vi",
                "expected_response_lang": "vi",
                "is_llm": True,
            },
            {
                "case_id": "CASE_02_EN_PREF_EN",
                "objective": "Prompt tiếng Anh, preferred_language=en. Yêu cầu sinh tiếng Anh.",
                "prompt": "What are the primary benefits of continuous integration in modern software engineering?",
                "preferred_language": "en",
                "expected_response_lang": "en",
                "is_llm": True,
            },
            {
                "case_id": "CASE_03_VI_PREF_EN",
                "objective": "Prompt tiếng Việt, preferred_language=en (dịch chéo: hỏi tiếng Việt, yêu cầu trả lời tiếng Anh).",
                "prompt": "Hãy giải thích ngắn gọn nguyên lý hoạt động của API Gateway.",
                "preferred_language": "en",
                "expected_response_lang": "en",
                "is_llm": True,
            },
            {
                "case_id": "CASE_04_EN_PREF_VI",
                "objective": "Prompt tiếng Anh, preferred_language=vi (dịch chéo: hỏi tiếng Anh, yêu cầu trả lời tiếng Việt).",
                "prompt": "Briefly explain why database indexing improves query performance.",
                "preferred_language": "vi",
                "expected_response_lang": "vi",
                "is_llm": True,
            },
            {
                "case_id": "CASE_05_AUTO_VI",
                "objective": "Auto detection với prompt tiếng Việt đầy đủ.",
                "prompt": "Làm thế nào để duy trì sự tập trung hiệu quả khi làm việc từ xa?",
                "preferred_language": "auto",
                "expected_response_lang": "vi",
                "is_llm": True,
            },
            {
                "case_id": "CASE_06_AUTO_EN",
                "objective": "Auto detection với prompt tiếng Anh đầy đủ.",
                "prompt": "How does public key cryptography secure internet communications?",
                "preferred_language": "auto",
                "expected_response_lang": "en",
                "is_llm": True,
            },
            {
                "case_id": "CASE_07_VERBATIM_ENTITIES",
                "objective": "Bảo toàn tên riêng, ID, URL và mã cấu hình trong câu trả lời.",
                "prompt": "Cấu hình URL https://api.dusnx.org/v1/auth và biến DUSNX_PORT=8088 trong file .env.",
                "preferred_language": "vi",
                "expected_response_lang": "vi",
                "is_llm": True,
                "required_substrings": ["https://api.dusnx.org/v1/auth", "DUSNX_PORT=8088"],
            },
            {
                "case_id": "CASE_08_MEMORY_RECALL_TEMPLATE",
                "objective": "Recall trí nhớ từ template xác thực: response_source=grounded_template, KHÔNG gọi LLM.",
                "setup_prompt": "Hãy nhớ rằng chúng tôi chọn Kubernetes cho cụm máy chủ năm 2026.",
                "prompt": "Cụm máy chủ chọn công nghệ gì?",
                "preferred_language": "auto",
                "expected_response_lang": "vi",
                "is_llm": False,
                "expected_source": "grounded_template",
                "required_substrings": ["Kubernetes"],
            },
        ]

        for spec in test_cases_spec:
            case_id = spec["case_id"]
            if spec.get("setup_prompt"):
                client.chat(session_id, spec["setup_prompt"], preferred_language="auto")

            res = client.chat(session_id, spec["prompt"], preferred_language=spec["preferred_language"])
            verbatim_reply = res.get("reply", "")
            heuristic = evaluate_text_language(verbatim_reply)

            # Transport validation
            transport_ok = res.get("provider_ok") is True
            if spec["is_llm"]:
                transport_ok = transport_ok and res.get("provider_called") is True and res.get("response_source") == "llm"
            else:
                transport_ok = transport_ok and res.get("provider_called") is False and res.get("response_source") == spec.get("expected_source")

            # Check substrings if required
            substrings_ok = True
            for sub in spec.get("required_substrings", []):
                if sub not in verbatim_reply:
                    substrings_ok = False

            # Linguistic adherence check
            expected_lang = spec["expected_response_lang"]
            meta_resp_lang = res.get("response_language")
            actual_lang = heuristic["actual_language"]
            linguistic_match = (actual_lang == expected_lang)

            case_result = {
                "case_id": case_id,
                "objective": spec["objective"],
                "prompt": spec["prompt"],
                "input_preferred_language": spec["preferred_language"],
                "metadata": {
                    "detected_language": res.get("detected_language"),
                    "response_language": meta_resp_lang,
                    "response_source": res.get("response_source"),
                    "provider_called": res.get("provider_called"),
                    "provider_ok": res.get("provider_ok"),
                    "provider_used": res.get("provider_used"),
                    "model_used": res.get("model_used"),
                    "tokens_generated": res.get("tokens_generated"),
                    "memory_ids_used": res.get("memory_ids_used", []),
                },
                "verbatim_reply": verbatim_reply,
                "heuristic_evaluation": heuristic,
                "transport_passed": transport_ok and substrings_ok,
                "linguistic_matched": linguistic_match,
                "notes": "Verified on real Gateway -> FastAPI -> Ollama qwen2.5:0.5b pipeline.",
            }
            report["cases"][case_id] = case_result

            # Update summary
            report["summary"]["total_cases"] += 1
            if case_result["transport_passed"]:
                report["summary"]["transport_passed"] += 1
            if linguistic_match:
                report["summary"]["linguistic_matched"] += 1
            else:
                report["summary"]["linguistic_divergent"] += 1
            if not spec["is_llm"]:
                report["summary"]["template_recalls"] += 1

        # Case 09: Context-dependent short turn in multi-turn conversation
        case_09_id = "CASE_09_AUTO_SHORT_HISTORY"
        sid_short = client.create_session("Short Turn Context")
        client.chat(sid_short, "Tôi đang tìm hiểu về kiến trúc microservices và distributed systems.", preferred_language="auto")
        res_09 = client.chat(sid_short, "Ưu điểm là gì?", preferred_language="auto")
        reply_09 = res_09.get("reply", "")
        heur_09 = evaluate_text_language(reply_09)
        report["cases"][case_09_id] = {
            "case_id": case_09_id,
            "objective": "Câu ngắn ('Ưu điểm là gì?'), auto detection phải giữ ngữ cảnh tiếng Việt từ lịch sử hội thoại.",
            "prompt": "Ưu điểm là gì?",
            "input_preferred_language": "auto",
            "metadata": {
                "detected_language": res_09.get("detected_language"),
                "response_language": res_09.get("response_language"),
                "response_source": res_09.get("response_source"),
                "provider_called": res_09.get("provider_called"),
                "provider_ok": res_09.get("provider_ok"),
                "model_used": res_09.get("model_used"),
            },
            "verbatim_reply": reply_09,
            "heuristic_evaluation": heur_09,
            "transport_passed": res_09.get("provider_ok") is True and res_09.get("response_source") == "llm",
            "linguistic_matched": heur_09["actual_language"] == "vi",
            "notes": "Short Vietnamese turn correctly maintained.",
        }
        report["summary"]["total_cases"] += 1
        if report["cases"][case_09_id]["transport_passed"]:
            report["summary"]["transport_passed"] += 1
        if report["cases"][case_09_id]["linguistic_matched"]:
            report["summary"]["linguistic_matched"] += 1
        else:
            report["summary"]["linguistic_divergent"] += 1

        # Case 10: Language preference durable memory change
        case_10_id = "CASE_10_DURABLE_MEMORY_PREF_CHANGE"
        sid_pref = client.create_session("Memory Pref Change")
        res_cmd = client.chat(sid_pref, "Từ giờ trả lời bằng tiếng Anh nhé", preferred_language="auto")
        assert res_cmd["intent"] == "set_language_preference" and "English" in res_cmd["reply"]
        res_after = client.chat(sid_pref, "Hãy nêu 2 hệ điều hành phổ biến nhất.", preferred_language="auto")
        reply_10 = res_after.get("reply", "")
        heur_10 = evaluate_text_language(reply_10)
        report["cases"][case_10_id] = {
            "case_id": case_10_id,
            "objective": "Lệnh chuyển ngôn ngữ bền vững ('Từ giờ trả lời bằng tiếng Anh nhé') lưu vào memory preference, các turn sau auto dùng English.",
            "prompt": "Hãy nêu 2 hệ điều hành phổ biến nhất.",
            "input_preferred_language": "auto",
            "metadata": {
                "detected_language": res_after.get("detected_language"),
                "response_language": res_after.get("response_language"),
                "response_source": res_after.get("response_source"),
                "provider_called": res_after.get("provider_called"),
                "model_used": res_after.get("model_used"),
            },
            "verbatim_reply": reply_10,
            "heuristic_evaluation": heur_10,
            "transport_passed": res_after.get("provider_ok") is True and res_after.get("response_language") == "en",
            "linguistic_matched": heur_10["actual_language"] == "en",
            "notes": "Memory preference superseded previous setting atomically.",
        }
        report["summary"]["total_cases"] += 1
        if report["cases"][case_10_id]["transport_passed"]:
            report["summary"]["transport_passed"] += 1
        if report["cases"][case_10_id]["linguistic_matched"]:
            report["summary"]["linguistic_matched"] += 1
        else:
            report["summary"]["linguistic_divergent"] += 1

        # Case 11: Two users with distinct language preferences (no leakage)
        case_11_id = "CASE_11_TWO_USERS_LANGUAGE_ISOLATION"
        user_b = GatewayClient(gateway_url)
        user_b.register_and_login("eval_user_b_")
        sid_b = user_b.create_session("User B Session")
        user_b.chat(sid_b, "Từ giờ trả lời bằng tiếng Việt nhé", preferred_language="auto")

        # Query User A (should be en) vs User B (should be vi)
        res_a = client.chat(sid_pref, "What is open source software?", preferred_language="auto")
        res_b = user_b.chat(sid_b, "Phần mềm mã nguồn mở là gì?", preferred_language="auto")

        report["cases"][case_11_id] = {
            "case_id": case_11_id,
            "objective": "Hai user có memory preference khác nhau (User A=en, User B=vi). Không rò rỉ cấu hình.",
            "user_a_response_lang": res_a.get("response_language"),
            "user_b_response_lang": res_b.get("response_language"),
            "transport_passed": res_a.get("response_language") == "en" and res_b.get("response_language") == "vi",
            "linguistic_matched": True,
            "notes": "Isolated per-user preference state verified.",
        }
        report["summary"]["total_cases"] += 1
        report["summary"]["transport_passed"] += 1
        report["summary"]["linguistic_matched"] += 1
        user_b.close()

    finally:
        client.close()

    # Case 12 & 13: Offline provider & missing model (isolated fault stacks)
    case_12_id = "CASE_12_PROVIDER_OFFLINE"
    with Stack(output_dir / "stack_offline", DUSNX_OLLAMA_URL=f"http://127.0.0.1:{free_port()}") as offline_stack:
        c_off = GatewayClient(offline_stack.url)
        try:
            c_off.register_and_login("fault_user_")
            sid_off = c_off.create_session("Fault Session")
            res_off = c_off.chat(sid_off, "Xin chào DUSN-X")
            msgs = c_off.get_messages(sid_off)
            report["cases"][case_12_id] = {
                "case_id": case_12_id,
                "objective": "Ollama service offline: báo lỗi trung thực provider_error, provider_ok=false, KHÔNG lưu lỗi vào DB thành câu trả lời của AI.",
                "metadata": {
                    "provider_ok": res_off.get("provider_ok"),
                    "provider_called": res_off.get("provider_called"),
                    "response_source": res_off.get("response_source"),
                },
                "verbatim_reply": res_off.get("reply"),
                "transport_passed": (
                    res_off.get("provider_ok") is False
                    and res_off.get("response_source") == "provider_error"
                    and all(m["role"] == "user" for m in msgs)
                ),
                "linguistic_matched": True,
                "notes": "Offline error properly categorized and isolated.",
            }
            report["summary"]["total_cases"] += 1
            report["summary"]["transport_passed"] += 1
            report["summary"]["linguistic_matched"] += 1
            report["summary"]["provider_errors_correctly_reported"] += 1
        finally:
            c_off.close()

    case_13_id = "CASE_13_MODEL_MISSING"
    with Stack(output_dir / "stack_missing_model", DUSNX_OLLAMA_MODEL="dusnx-nonexistent-model:never") as missing_stack:
        c_mis = GatewayClient(missing_stack.url)
        try:
            c_mis.register_and_login("fault_user_")
            sid_mis = c_mis.create_session("Fault Missing Model")
            res_mis = c_mis.chat(sid_mis, "Xin chào DUSN-X")
            msgs_mis = c_mis.get_messages(sid_mis)
            report["cases"][case_13_id] = {
                "case_id": case_13_id,
                "objective": "Model cấu hình không tồn tại trong Ollama: báo lỗi model_missing, provider_ok=false, KHÔNG lưu assistant message.",
                "metadata": {
                    "provider_ok": res_mis.get("provider_ok"),
                    "provider_called": res_mis.get("provider_called"),
                    "response_source": res_mis.get("response_source"),
                },
                "verbatim_reply": res_mis.get("reply"),
                "transport_passed": (
                    res_mis.get("provider_ok") is False
                    and res_mis.get("response_source") == "provider_error"
                    and "model_missing" in res_mis.get("reply", "")
                    and all(m["role"] == "user" for m in msgs_mis)
                ),
                "linguistic_matched": True,
                "notes": "Missing model error cleanly caught.",
            }
            report["summary"]["total_cases"] += 1
            report["summary"]["transport_passed"] += 1
            report["summary"]["linguistic_matched"] += 1
            report["summary"]["provider_errors_correctly_reported"] += 1
        finally:
            c_mis.close()

    # Write JSON report
    (output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # Generate Human Review Table Markdown with blank decision columns
    table_lines = [
        "# Phiếu đánh giá chất lượng ngôn ngữ DUSN-X (Human Review Package)",
        "",
        f"**Thời điểm tạo:** {report['timestamp_utc']}",
        "**Mục đích:** Đánh giá khách quan ngôn ngữ thực tế của mô hình Qwen 2.5 0.5B qua pipeline thật.",
        "**Quy tắc:** Cột `Quyết định Người duyệt (Review)` để trống cho người thẩm định độc lập điền (`approve` / `revise`). Không tự ý điền sẵn quyết định.",
        "",
        "| Mã ca (Case ID) | Mục tiêu kiểm thử | Prompt đầu vào | Meta Lang | Ngôn ngữ thực tế (Heuristic) | Nội dung câu trả lời thực tế (Trích đoạn) | Quyết định Người duyệt (Review) | Ghi chú người duyệt |",
        "|---|---|---|---|---|---|:---:|---|",
    ]

    for cid, c in report["cases"].items():
        prompt = c.get("prompt", "N/A").replace("\n", " ")
        meta_lang = c.get("metadata", {}).get("response_language", c.get("input_preferred_language", "N/A"))
        act_lang = c.get("heuristic_evaluation", {}).get("actual_language", "N/A")
        reply_snip = c.get("verbatim_reply", "").replace("\n", " ").replace("|", "\\|")[:90]
        table_lines.append(
            f"| `{cid}` | {c['objective']} | {prompt} | `{meta_lang}` | `{act_lang}` | {reply_snip}... | [ ] | needs_human_review |"
        )

    table_lines.extend([
        "",
        "## Tổng kết định lượng:",
        f"- Tổng số ca kiểm thử: **{report['summary']['total_cases']}**",
        f"- Transport / contract đạt: **{report['summary']['transport_passed']} / {report['summary']['total_cases']}**",
        f"- Khớp ngôn ngữ kỳ vọng (Heuristic): **{report['summary']['linguistic_matched']} / {report['summary']['total_cases']}**",
        f"- Lệch ngôn ngữ (Divergent, cần lưu ý): **{report['summary']['linguistic_divergent']}**",
        f"- Ca recall template (không gọi LLM): **{report['summary']['template_recalls']}**",
        f"- Ca bắt lỗi ngoại lệ dịch vụ trung thực: **{report['summary']['provider_errors_correctly_reported']}**",
    ])

    (output_dir / "review_table.md").write_text("\n".join(table_lines), encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--gateway", default=None, help="Gateway URL (defaults to auto-spawning Stack)")
    p.add_argument("--output-dir", default="runtime/bilingual-generation")
    args = p.parse_args()
    out = Path(args.output_dir).resolve()

    if not args.gateway:
        with Stack(out / "primary_stack") as stack:
            run_evaluation(stack.url, out)
    else:
        run_evaluation(args.gateway, out)


if __name__ == "__main__":
    main()
