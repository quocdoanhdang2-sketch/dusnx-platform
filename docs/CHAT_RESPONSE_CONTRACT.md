# Hợp đồng câu trả lời và nguồn trí nhớ

`POST /v1/chat`, hoặc `/api/v1/chat` qua Gateway. Gateway là HttpClient streaming proxy, giữ body/status từ FastAPI; không có schema chat C# riêng để đổi tên/bỏ trường. Auth dùng opaque token, không phải JWT.

Luồng: xác thực user/session → SQL lấy active memory đúng user và project/global scope, xếp hạng/top 15 → chọn theo chủ đề → template recall/clarification **không gọi provider**, hoặc chọn memory cho prompt rồi gọi provider → lưu assistant message khi thành công → JSON qua Gateway → Web hiển thị số memory được trích và nguồn câu trả lời.

| Trường | Nghĩa |
|---|---|
| candidate_memory_ids | Top 15 ứng viên sau lọc owner, scope, active; có thể còn mục không liên quan. Lấy trước mutation của lượt. |
| memory_ids_used | ID được câu template/application trực tiếp trích/dựa vào. Không còn là toàn bộ retrieval. LLM tự do chưa có cơ chế xác minh citations nên để `[]`. |
| prompt_memory_ids | Chỉ ID thực sự đưa vào prompt trong lượt đó; không tự coi là citations. Template luôn `[]`. |
| provider_called | Đã thử HTTP generation ở lượt này (kể cả lỗi mạng); không suy từ health. Mock/thiếu cấu hình/template là false. |
| response_source | grounded_template, clarification, application_rule, llm, mock hoặc provider_error. |
| provider_used | Provider thực sự đã gọi: ollama/openai, kể cả attempt thất bại; null khi không gọi. |
| model_used | Tên model trả về từ generation thành công, không lấy từ health; null khi không đo được. |
| tokens_generated | Số token provider báo, không tự ước lượng; null cho template/lỗi. |
| provider_ok | Tương thích cũ: lượt trả lời thành công, bao gồm template không cần provider. False cho lỗi; **không đồng nghĩa provider_called**. |
| answer_source | Alias cũ giữ tương thích: active_memory_extract/provider/application_rule. Dùng response_source cho phân loại mới. |
| routing_source/runtime_mode | Nguồn định tuyến/model nạp, không phải nguồn sinh văn bản. |

Tạo/sửa/hủy memory là application_rule. Xác nhận sửa có thể trích cả bản cũ/mới với nhãn rõ để audit; bản cũ không là active candidate cho recall tiếp theo. memory_ids_used được lưu cùng message, nên lịch sử Web giữ số trí nhớ đúng. Trường nguồn mới hiện dành cho response lượt sống; lịch sử cũ không được tự gán ngược là LLM.

Chọn theo từ khóa chủ đề phân biệt, bỏ từ chung; hỏi tổng hợp rõ có thể chọn nhiều memory, không phân biệt được thì hỏi rõ. Không hardcode thực thể. Đây là heuristic tiếng Việt, không phải hiểu ngữ nghĩa hoàn chỉnh: paraphrase/đồng nghĩa và hơn 15 memory còn là giới hạn. LLM có thể sinh sai hoặc sai ngôn ngữ dù transport thành công.

Retry lượt provider thất bại không tăng thêm event/state version hoặc tạo memory. Retry confirmation dùng transaction idempotent sẵn có; đã sửa để không tăng state lần nữa. Không thay logic SQL supersede nguyên tử.

Kiểm chứng: `python scripts/verify_chat_provenance.py --output runtime/chat-provenance.json`. Script dùng user thử mới, bỏ credentials khỏi evidence. Template recall và Ollama generation là hai phép kiểm chứng riêng; health không chứng minh generation.
