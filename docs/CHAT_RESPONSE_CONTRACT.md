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

Tuần4 bổ sung `request_id` tùy chọn, Web luôn gửi và giữ nguyên ID khi retry cùng
session/message/project. Receipt per-user được ghi bền; response thành công replay
nguyên message/state version, không chạy mutation/provider lần nữa. Replay có
`response_source=replay`, `replayed=true`, `provider_called=false`, provider/model/token
null; nguồn lần sinh gốc ở `original_provenance`. Không giả là lượt gọi Ollama mới.
ID dùng cho nội dung khác trả409. Reservation dở dang trả409 kết quả chưa xác định,
không tự thử lại thao tác ghi. Lỗi provider đã xác định cho phép explicit retry,
giữ state/event của lần đầu. Client legacy thiếu ID không có guarantee tương đương.
`state_reset/reset_reason` phản ánh reset tương thích, state malformed bị từ chối409.
GET state trả model/schema đã lưu và `state_compatible`, không gán model mới cho blob cũ.

Kiểm chứng: `python scripts/verify_chat_provenance.py --output runtime/chat-provenance.json`. Script dùng user thử mới, bỏ credentials khỏi evidence. Template recall và Ollama generation là hai phép kiểm chứng riêng; health không chứng minh generation.

## Chất lượng generation và metadata provider

Prompt provider giới hạn theo ngôn ngữ phản hồi, yêu cầu hiện tại, lịch sử gần nhất trong cùng session và memory hiệu lực. Mô tả chung về sản phẩm DUSN-X không được chèn vào ngữ cảnh trả lời. Câu người dùng nói trong lịch sử được đánh dấu là thông tin do người dùng cung cấp, không phải sự kiện đã xác minh. Ứng dụng hỏi làm rõ khi câu tiếp nối không có chủ đề trước đó.

`provider_call_count` ghi số lần provider thực sự được gọi. Tối đa một lần gọi sửa được thực hiện khi phát hiện rõ sai ngôn ngữ hoặc đổi literal bắt buộc; retry request vẫn đi qua receipt/idempotency hiện có. Nếu câu trả lời vẫn không đạt quality guard, API trả `provider_error` và không lưu nó thành assistant message. `quality_status` là trạng thái ngôn ngữ tự động thận trọng, không phải đánh giá ngữ nghĩa.

`done_reason` ghi metadata hoàn tất của provider khi có (`stop`, `length` hoặc giá trị riêng của provider). `DUSNX_OLLAMA_NUM_PREDICT` mặc định là 512. `length` là bằng chứng provider chạm giới hạn; đạt đúng số token cấu hình mà không có lý do kết thúc chỉ tạo cờ chưa chắc chắn. Thiếu dấu câu cuối không tự động là lỗi. `sanitizer_changed` và `raw_output_sha256` giúp quan sát sanitizer mà không để lộ raw output mặc định. `DUSNX_CAPTURE_RAW_GENERATION=1` chỉ mở raw/sanitized text cho lượt thu evidence tổng hợp được cấu hình rõ trên máy local; không bật với dữ liệu người dùng hoặc traffic production.

Harness bilingual báo cáo riêng transport, ngôn ngữ, tác vụ/ngữ cảnh, thực thể, rò rỉ/lặp chỉ dẫn và trạng thái hoàn tất. Kiểm tra ngôn ngữ/script và hoàn tất là heuristic. Kết quả tác vụ không có rubric xác định giữ trạng thái `uncertain` và làm strict quality mode thất bại; không gọi đó là independent human review. `scripts/verify_chat_provenance.py` ghi rõ phạm vi transport/provenance và ngôn ngữ phản hồi, đồng thời đánh dấu semantic task review là chưa đánh giá.
