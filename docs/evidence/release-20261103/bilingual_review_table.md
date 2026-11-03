# Phiếu đánh giá chất lượng ngôn ngữ DUSN-X (Human Review Package)

**Thời điểm tạo:** 2026-11-03T02:56:54.643136+00:00
**Mục đích:** Đánh giá khách quan ngôn ngữ thực tế của mô hình Qwen 2.5 0.5B qua pipeline thật.
**Quy tắc:** Cột `Quyết định Người duyệt (Review)` để trống cho người thẩm định độc lập điền (`approve` / `revise`). Không tự ý điền sẵn quyết định.

| Mã ca (Case ID) | Loại ca (Type) | Mục tiêu kiểm thử | Prompt đầu vào | Meta Lang | Ngôn ngữ thực tế (Heuristic) | Đánh giá Heuristic | Nội dung câu trả lời thực tế (Trích đoạn) | Quyết định Người duyệt (Review) | Ghi chú người duyệt |
|---|---|---|---|---|---|:---:|---|:---:|---|
| `CASE_01_VI_PREF_VI` | `llm_generation` | Prompt tiếng Việt, preferred_language=vi. Yêu cầu sinh tiếng Việt. | Hệ thống DUSN-X có những tính năng cốt lõi nào? | `vi` | `vi` | `matched` | Dữ liệu:  1. Quản lý trí nhớ dài hạn (ghi nhớ và cập nhật quyết định cá nhân) 2. Định... | [ ] | needs_human_review |
| `CASE_02_EN_PREF_EN` | `llm_generation` | Prompt tiếng Anh, preferred_language=en. Yêu cầu sinh tiếng Anh. | What are the primary benefits of continuous integration in modern software engineering? | `en` | `en` | `matched` | Continuous Integration (CI) enhances collaboration and reduces defects by allowing de... | [ ] | needs_human_review |
| `CASE_03_VI_PREF_EN` | `llm_generation` | Prompt tiếng Việt, preferred_language=en (dịch chéo: hỏi tiếng Việt, yêu cầu trả lời tiếng Anh). | Hãy giải thích ngắn gọn nguyên lý hoạt động của API Gateway. | `en` | `en` | `matched` | API Gateway operates by routing incoming requests to appropriate endpoints based on s... | [ ] | needs_human_review |
| `CASE_04_EN_PREF_VI` | `llm_generation` | Prompt tiếng Anh, preferred_language=vi (dịch chéo: hỏi tiếng Anh, yêu cầu trả lời tiếng Việt). | Briefly explain why database indexing improves query performance. | `vi` | `vi` | `matched` | "Điều này giúp tăng hiệu suất kiểm tra và tìm kiếm dữ liệu."... | [ ] | needs_human_review |
| `CASE_05_AUTO_VI` | `llm_generation` | Auto detection với prompt tiếng Việt đầy đủ. | Làm thế nào để duy trì sự tập trung hiệu quả khi làm việc từ xa? | `vi` | `vi` | `matched` | Để duy trì sự tập trung hiệu quả trong thời gian làm việc từ xa, bạn có thể thực hiện... | [ ] | needs_human_review |
| `CASE_06_AUTO_EN` | `llm_generation` | Auto detection với prompt tiếng Anh đầy đủ. | How does public key cryptography secure internet communications? | `en` | `en` | `matched` | Public Key Cryptography (PKC) secures Internet Communications by using a shared secre... | [ ] | needs_human_review |
| `CASE_07_VERBATIM_ENTITIES` | `verbatim_entities` | Bảo toàn tên riêng, ID, URL và mã cấu hình trong câu trả lời. | Cấu hình URL https://api.dusnx.org/v1/auth và biến DUSNX_PORT=8088 trong file .env. | `vi` | `vi` | `matched` | Dưới đây là hướng dẫn cấu hình bằng tiếng Việt:  - **URL**:    - `https://api.dusnx.o... | [ ] | needs_human_review |
| `CASE_08_MEMORY_RECALL_TEMPLATE` | `template_recall` | Recall trí nhớ từ template xác thực: response_source=grounded_template, KHÔNG gọi LLM. | Cụm máy chủ chọn công nghệ gì? | `vi` | `vi` | `not_applicable` | Theo trí nhớ đang hiệu lực: chúng tôi chọn Kubernetes cho cụm máy chủ năm 2026.... | [ ] | needs_human_review |
| `CASE_09_AUTO_SHORT_HISTORY` | `llm_generation` | Câu ngắn ('Ưu điểm là gì?'), auto detection phải giữ ngữ cảnh tiếng Việt từ lịch sử hội thoại. | Ưu điểm là gì? | `vi` | `vi` | `matched` | Uwien, bạn đang tìm hiểu về kiến trúc microservices và distributed systems. Dưới đây ... | [ ] | needs_human_review |
| `CASE_10_DURABLE_MEMORY_PREF_CHANGE` | `llm_generation` | Lệnh chuyển ngôn ngữ bền vững ('Từ giờ trả lời bằng tiếng Anh nhé') lưu vào memory preference, các turn sau auto dùng English. | Hãy nêu 2 hệ điều hành phổ biến nhất. | `en` | `en` | `matched` | The two most popular operating systems are Windows and macOS.... | [ ] | needs_human_review |
| `CASE_11_TWO_USERS_LANGUAGE_ISOLATION` | `user_preference_isolation` | Hai user có memory preference khác nhau (User A=en, User B=vi). Không rò rỉ cấu hình. | User A: 'What is open source software?' | User B: 'Phần mềm mã nguồn mở là gì?' | `auto` | `N/A` | `matched` | User A: Open-source software (OSS) refers to computer programs whose code can be acce... | [ ] | needs_human_review |
| `CASE_12_PROVIDER_OFFLINE` | `expected_provider_error` | Ollama service offline: báo lỗi trung thực provider_error, provider_ok=false, KHÔNG lưu lỗi vào DB thành câu trả lời của AI. | Xin chào DUSN-X | `auto` | `vi` | `not_applicable` | [Không kết nối được Ollama (unreachable)]... | [ ] | needs_human_review |
| `CASE_13_MODEL_MISSING` | `expected_provider_error` | Model cấu hình không tồn tại trong Ollama: báo lỗi model_missing, provider_ok=false, KHÔNG lưu assistant message. | Xin chào DUSN-X | `auto` | `vi` | `not_applicable` | [Model cấu hình không tồn tại trong Ollama (model_missing)]... | [ ] | needs_human_review |

## Tổng kết định lượng:
- Ca có cờ nội dung lặp (không phải đánh giá factuality): **0**
- Tổng số ca kiểm thử: **13**
- Contract đạt chuẩn bắt buộc: **13 / 13** (Thất bại: **0**)
- Số ca LLM generation đủ contract (không đếm setup hoặc từng response của ca isolation): **9**
- Số ca Template recall (không gọi LLM): **1**
- Số ca bắt lỗi Provider ngoại lệ đúng chuẩn: **2**
- Số ca đủ điều kiện đánh giá ngôn ngữ: **10**
  + Khớp ngôn ngữ kỳ vọng (Matched): **10 / 10**
  + Lệch ngôn ngữ (Divergent): **0 / 10**
  + Chưa xác định rõ (Uncertain): **0 / 10**