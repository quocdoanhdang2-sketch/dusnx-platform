# Phiếu đánh giá chất lượng ngôn ngữ DUSN-X (Human Review Package)

**Thời điểm tạo:** 2026-11-02T16:27:52.098191+00:00
**Mục đích:** Đánh giá khách quan ngôn ngữ thực tế của mô hình Qwen 2.5 0.5B qua pipeline thật.
**Quy tắc:** Cột `Quyết định Người duyệt (Review)` để trống cho người thẩm định độc lập điền (`approve` / `revise`). Không tự ý điền sẵn quyết định.

| Mã ca (Case ID) | Loại ca (Type) | Mục tiêu kiểm thử | Prompt đầu vào | Meta Lang | Ngôn ngữ thực tế (Heuristic) | Đánh giá Heuristic | Nội dung câu trả lời thực tế (Trích đoạn) | Quyết định Người duyệt (Review) | Ghi chú người duyệt |
|---|---|---|---|---|---|:---:|---|:---:|---|
| `CASE_01_VI_PREF_VI` | `llm_generation` | Prompt tiếng Việt, preferred_language=vi. Yêu cầu sinh tiếng Việt. | Hệ thống DUSN-X có những tính năng cốt lõi nào? | `vi` | `vi` | `matched` | Hệ thống DUSN-X có các tính năng chính bao gồm:  1. Mô phỏng và phân tích dữ liệu 2. ... | [ ] | needs_human_review |
| `CASE_02_EN_PREF_EN` | `llm_generation` | Prompt tiếng Anh, preferred_language=en. Yêu cầu sinh tiếng Anh. | What are the primary benefits of continuous integration in modern software engineering? | `en` | `en` | `matched` | Continuous integration (CI) is a software development practice that involves the inte... | [ ] | needs_human_review |
| `CASE_03_VI_PREF_EN` | `llm_generation` | Prompt tiếng Việt, preferred_language=en (dịch chéo: hỏi tiếng Việt, yêu cầu trả lời tiếng Anh). | Hãy giải thích ngắn gọn nguyên lý hoạt động của API Gateway. | `en` | `vi` | `divergent` | API Gateway là một hệ thống quản lý API (Application Programming Interface) giúp các ... | [ ] | needs_human_review |
| `CASE_04_EN_PREF_VI` | `llm_generation` | Prompt tiếng Anh, preferred_language=vi (dịch chéo: hỏi tiếng Anh, yêu cầu trả lời tiếng Việt). | Briefly explain why database indexing improves query performance. | `vi` | `en` | `divergent` | Database indexing improves query performance by allowing the database to quickly loca... | [ ] | needs_human_review |
| `CASE_05_AUTO_VI` | `llm_generation` | Auto detection với prompt tiếng Việt đầy đủ. | Làm thế nào để duy trì sự tập trung hiệu quả khi làm việc từ xa? | `vi` | `vi` | `matched` | Duy trì sự tập trung hiệu quả khi làm việc từ xa có thể thay đổi theo từng công việc ... | [ ] | needs_human_review |
| `CASE_06_AUTO_EN` | `llm_generation` | Auto detection với prompt tiếng Anh đầy đủ. | How does public key cryptography secure internet communications? | `en` | `en` | `matched` | Public key cryptography secures internet communications by enabling secure key exchan... | [ ] | needs_human_review |
| `CASE_07_VERBATIM_ENTITIES` | `verbatim_entities` | Bảo toàn tên riêng, ID, URL và mã cấu hình trong câu trả lời. | Cấu hình URL https://api.dusnx.org/v1/auth và biến DUSNX_PORT=8088 trong file .env. | `vi` | `vi` | `matched` | Dưới đây là cấu hình URL và biến DUSNX_PORT cho API DUSN-X:  - URL: `https://api.dusn... | [ ] | needs_human_review |
| `CASE_08_MEMORY_RECALL_TEMPLATE` | `template_recall` | Recall trí nhớ từ template xác thực: response_source=grounded_template, KHÔNG gọi LLM. | Cụm máy chủ chọn công nghệ gì? | `vi` | `vi` | `not_applicable` | Theo trí nhớ đang hiệu lực: chúng tôi chọn Kubernetes cho cụm máy chủ năm 2026.... | [ ] | needs_human_review |
| `CASE_09_AUTO_SHORT_HISTORY` | `llm_generation` | Câu ngắn ('Ưu điểm là gì?'), auto detection phải giữ ngữ cảnh tiếng Việt từ lịch sử hội thoại. | Ưu điểm là gì? | `vi` | `vi` | `matched` | Ưu điểm là: Microservices giúp giảm tải hệ thống, tăng hiệu suất và dễ dàng quản lý. ... | [ ] | needs_human_review |
| `CASE_10_DURABLE_MEMORY_PREF_CHANGE` | `llm_generation` | Lệnh chuyển ngôn ngữ bền vững ('Từ giờ trả lời bằng tiếng Anh nhé') lưu vào memory preference, các turn sau auto dùng English. | Hãy nêu 2 hệ điều hành phổ biến nhất. | `en` | `vi` | `divergent` | 2.1 Windows: Được phát triển bởi Microsoft và được sử dụng rộng rãi trong nhiều hệ th... | [ ] | needs_human_review |
| `CASE_11_TWO_USERS_LANGUAGE_ISOLATION` | `user_preference_isolation` | Hai user có memory preference khác nhau (User A=en, User B=vi). Không rò rỉ cấu hình. | User A: 'What is open source software?' | User B: 'Phần mềm mã nguồn mở là gì?' | `auto` | `N/A` | `matched` | User A: Open source software (OS) refers to software that is made available to the pu... | [ ] | needs_human_review |
| `CASE_12_PROVIDER_OFFLINE` | `expected_provider_error` | Ollama service offline: báo lỗi trung thực provider_error, provider_ok=false, KHÔNG lưu lỗi vào DB thành câu trả lời của AI. | Xin chào DUSN-X | `auto` | `vi` | `not_applicable` | [Không kết nối được Ollama (unreachable)]... | [ ] | needs_human_review |
| `CASE_13_MODEL_MISSING` | `expected_provider_error` | Model cấu hình không tồn tại trong Ollama: báo lỗi model_missing, provider_ok=false, KHÔNG lưu assistant message. | Xin chào DUSN-X | `auto` | `vi` | `not_applicable` | [Model cấu hình không tồn tại trong Ollama (model_missing)]... | [ ] | needs_human_review |

## Tổng kết định lượng:
- Tổng số ca kiểm thử: **13**
- Contract đạt chuẩn bắt buộc: **13 / 13** (Thất bại: **0**)
- Số ca LLM generation thật thành công: **9**
- Số ca Template recall (không gọi LLM): **1**
- Số ca bắt lỗi Provider ngoại lệ đúng chuẩn: **2**
- Số ca đủ điều kiện đánh giá ngôn ngữ: **10**
  + Khớp ngôn ngữ kỳ vọng (Matched): **7 / 10**
  + Lệch ngôn ngữ (Divergent): **3 / 10**
  + Chưa xác định rõ (Uncertain): **0 / 10**