# Phiếu đánh giá chất lượng ngôn ngữ DUSN-X (Human Review Package)

**Thời điểm tạo:** 2026-11-03T11:45:58.693240+00:00
**Mục đích:** Đánh giá khách quan ngôn ngữ thực tế của mô hình Qwen 2.5 0.5B qua pipeline thật.
**Quy tắc:** Cột `Quyết định Người duyệt (Review)` để trống cho người thẩm định độc lập điền (`approve` / `revise`). Không tự ý điền sẵn quyết định.

| Mã ca (Case ID) | Loại ca (Type) | Mục tiêu kiểm thử | Prompt đầu vào | Meta Lang | Ngôn ngữ thực tế (Heuristic) | Đánh giá Heuristic | Nội dung câu trả lời thực tế (Trích đoạn) | Quyết định Người duyệt (Review) | Ghi chú người duyệt |
|---|---|---|---|---|---|:---:|---|:---:|---|
| `CASE_01_VI_PREF_VI` | `application_clarification` | Câu hỏi về tính năng sản phẩm nội bộ không có tài liệu grounding phải được làm rõ thay vì tự sinh thông tin. | Hệ thống DUSN-X có những tính năng cốt lõi nào? | `vi` | `vi` | `matched` | Tôi chưa có tài liệu đã xác minh về tính năng của DUSN-X. Bạn gửi đặc tả hoặc tài liệ... | [ ] | needs_human_review |
| `CASE_02_EN_PREF_EN` | `llm_generation` | Prompt tiếng Anh, preferred_language=en. Yêu cầu sinh tiếng Anh. | What are the primary benefits of continuous integration in modern software engineering? | `en` | `en` | `matched` | Continuous Integration (CI) is an approach where developers automatically integrate t... | [ ] | needs_human_review |
| `CASE_03_VI_PREF_EN` | `llm_generation` | Prompt tiếng Việt, preferred_language=en (dịch chéo: hỏi tiếng Việt, yêu cầu trả lời tiếng Anh). | Hãy giải thích ngắn gọn nguyên lý hoạt động của API Gateway. | `en` | `en` | `matched` | The API gateway is a web service that acts as an intermediary between clients, such a... | [ ] | needs_human_review |
| `CASE_04_EN_PREF_VI` | `llm_generation` | Prompt tiếng Anh, preferred_language=vi (dịch chéo: hỏi tiếng Anh, yêu cầu trả lời tiếng Việt). | Briefly explain why database indexing improves query performance. | `vi` | `vi` | `matched` | Để cải thiện hiệu suất của một hệ thống dữ liệu, việc sử dụng index trong nó có thể g... | [ ] | needs_human_review |
| `CASE_05_AUTO_VI` | `llm_generation` | Auto detection với prompt tiếng Việt đầy đủ. | Làm thế nào để duy trì sự tập trung hiệu quả khi làm việc từ xa? | `vi` | `vi` | `matched` | Đảm bảo rằng bạn đang sử dụng thiết bị và hệ thống máy tính của mình một cách hợp lý,... | [ ] | needs_human_review |
| `CASE_06_AUTO_EN` | `llm_generation` | Auto detection với prompt tiếng Anh đầy đủ. | How does public key cryptography secure internet communications? | `en` | `en` | `matched` | Public-key cryptography is used in Internet communication because it provides an addi... | [ ] | needs_human_review |
| `CASE_07_VERBATIM_ENTITIES` | `verbatim_entities` | Bảo toàn tên riêng, ID, URL và mã cấu hình trong câu trả lời. | Cấu hình URL https://api.dusnx.org/v1/auth và biến DUSNX_PORT=8088 trong file .env. | `vi` | `vi` | `matched` | Cấu hình URL https://api.dusnx.org/v1/auth và biến DUSNX_PORT=8088 trong file .env.... | [ ] | needs_human_review |
| `VARIANT_14_ENTITY_CONFIG_WEBHOOK` | `verbatim_entities` | Tạo cấu hình .env, bảo toàn URL và assignment chính xác; không được chỉ chép prompt. | Viết một đoạn cấu hình .env cho webhook, giữ URL https://hooks.example.net/v2/events và đặt WEBHOOK_RETRY_LIMIT=7. Giải thích ngắn gọn cách áp dụng. | `vi` | `vi` | `matched` | Để hoàn thành yêu cầu này:  - **URL:** `https://hooks.example.net/v2/events`   - Đây ... | [ ] | needs_human_review |
| `VARIANT_15_ENTITY_CONFIG_QUERY_URL` | `verbatim_entities` | Tạo cấu hình .env, giữ nguyên URL có query/punctuation và giá trị không bị đổi. | Provide an example .env setting for the cache endpoint https://edge.example.org/api/v3?mode=fast, and set CACHE_TTL_SECONDS=45; include one sentence explaining where to put it. | `en` | `en` | `matched` | To provide a complete solution that includes variables in `.env`, we can use:  ```pla... | [ ] | needs_human_review |
| `CASE_08_MEMORY_RECALL_TEMPLATE` | `template_recall` | Recall trí nhớ từ template xác thực: response_source=grounded_template, KHÔNG gọi LLM. | Cụm máy chủ chọn công nghệ gì? | `vi` | `vi` | `not_applicable` | Theo trí nhớ đang hiệu lực: chúng tôi chọn Kubernetes cho cụm máy chủ năm 2026.... | [ ] | needs_human_review |
| `CASE_09_AUTO_SHORT_HISTORY` | `application_clarification` | Câu hỏi mơ hồ sau khi người dùng nêu hai chủ đề phải hỏi chọn chủ đề thay vì đoán. | Ưu điểm là gì? | `vi` | `vi` | `matched` | Bạn muốn hỏi ưu điểm của chủ đề nào trong các chủ đề vừa nêu?... | [ ] | needs_human_review |
| `VARIANT_16_TOPIC_SHIFT_FOLLOWUP` | `llm_generation` | Câu tiếp nối sau khi đổi chủ đề phải bám chủ đề gần nhất trong cùng session. | Những rủi ro của nó là gì? | `vi` | `vi` | `mixed` | Rủi ro chính của công nghệ Public Key Cryptography (PKC) bao gồm:  1. Tính bảo mật mã... | [ ] | needs_human_review |
| `VARIANT_17_AMBIGUOUS_NEW_SESSION` | `clarification` | Không đoán chủ đề cho câu hỏi thiếu antecedent trong session mới. | Ưu điểm là gì? | `N/A` | `N/A` | `matched` | Hiện tại tôi chưa có bối cảnh hoặc quyết định nào trước đó để nhắc lại. Bạn có thể ch... | [ ] | needs_human_review |
| `CASE_10_DURABLE_MEMORY_PREF_CHANGE` | `llm_generation` | Lệnh chuyển ngôn ngữ bền vững ('Từ giờ trả lời bằng tiếng Anh nhé') lưu vào memory preference, các turn sau auto dùng English. | Hãy nêu 2 hệ điều hành phổ biến nhất. | `en` | `en` | `matched` | Two popular operating systems are Windows and macOS.... | [ ] | needs_human_review |
| `CASE_11_TWO_USERS_LANGUAGE_ISOLATION` | `user_preference_isolation` | Hai user có memory preference khác nhau (User A=en, User B=vi). Không rò rỉ cấu hình. | User A: 'What is open source software?' | User B: 'Phần mềm mã nguồn mở là gì?' | `auto` | `N/A` | `matched` | User A: Open-source software (OSS) refers to computer programs that are made availabl... | [ ] | needs_human_review |
| `VARIANT_18_USER_SESSION_CONTEXT_ISOLATION` | `clarification` | Không rò rỉ antecedent từ user A hoặc session khác sang session mới của user B. | Ưu điểm là gì? | `vi` | `N/A` | `matched` | Hiện tại tôi chưa có bối cảnh hoặc quyết định nào trước đó để nhắc lại. Bạn có thể ch... | [ ] | needs_human_review |
| `CASE_12_PROVIDER_OFFLINE` | `expected_provider_error` | Ollama service offline: báo lỗi trung thực provider_error, provider_ok=false, KHÔNG lưu lỗi vào DB thành câu trả lời của AI. | Xin chào DUSN-X | `auto` | `vi` | `not_applicable` | [Không kết nối được Ollama (unreachable)]... | [ ] | needs_human_review |
| `CASE_13_MODEL_MISSING` | `expected_provider_error` | Model cấu hình không tồn tại trong Ollama: báo lỗi model_missing, provider_ok=false, KHÔNG lưu assistant message. | Xin chào DUSN-X | `auto` | `vi` | `not_applicable` | [Model cấu hình không tồn tại trong Ollama (model_missing)]... | [ ] | needs_human_review |

## Tổng kết định lượng:
- Ca có cờ nội dung lặp (không phải đánh giá factuality): **1**
- Tổng số ca kiểm thử: **18**
- Contract đạt chuẩn bắt buộc: **14 / 18** (Thất bại: **4**)
- Số ca LLM generation đủ contract (không đếm setup hoặc từng response của ca isolation): **6**
- Số ca Template recall (không gọi LLM): **1**
- Số ca bắt lỗi Provider ngoại lệ đúng chuẩn: **2**
- Số ca đủ điều kiện đánh giá ngôn ngữ: **11**
  + Khớp ngôn ngữ kỳ vọng (Matched): **10 / 11**
  + Lệch ngôn ngữ (Divergent): **0 / 11**
  + Chưa xác định rõ (Uncertain): **0 / 11**