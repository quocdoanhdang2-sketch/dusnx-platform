# Demo 6 phút và báo cáo học máy

## Demo sản phẩm thật

| Thời gian | Thao tác | Ý nghĩa/bằng chứng |
|---|---|---|
| 0:00–0:45 | Mở Web/health, giải thích kiến trúc | Web → Gateway → FastAPI, router/state, SQLite, Ollama; hai model riêng |
| 0:45–1:20 | Đăng ký/đăng nhập tài khoản demo mới | Opaque token; không hiển thị token/password khi quay màn hình |
| 1:20–2:00 | “Hãy nhớ rằng chúng tôi chọn PostgreSQL cho cơ sở dữ liệu.”; mở memory | Memory ứng dụng đã xác nhận ghi; không nói neural model tự lưu |
| 2:00–3:00 | “Đổi PostgreSQL sang MongoDB”; xem pending, hủy; đề xuất lại và xác nhận | Bản cũ giữ nguyên khi hủy; xác nhận tạo version 2, bản cũ inactive |
| 3:00–3:45 | Tạo phiên mới; hỏi “Cơ sở dữ liệu được chọn là gì?” | MongoDB; badge trích memory, provider_called=false |
| 3:45–4:30 | Lưu AWS cho hạ tầng; hỏi “Quyết định hiện tại của tôi là gì?” | Hỏi làm rõ; không chọn nhầm giữa hai loại quyết định |
| 4:30–5:15 | Hỏi một câu viết ngắn về đọc sách; mở health/provenance | LLM base thực, model đúng; generation tách khỏi template và routing |
| 5:15–6:00 | Trình bày kết quả và giới hạn | Candidate giữ evaluation; AI provisional; không superiority, không native Office |

Chạy bằng [Windows runbook](WINDOWS_NATIVE_RUNBOOK.md). Nội dung LLM không cố định;
provider lỗi phải hiển thị lỗi và thử lại an toàn, không diễn demo thành công giả.
Không dùng Web platform dropdown để chứng minh Office/Zalo tích hợp thật.

## Bảy bước học máy — tách router và LLM

| Bước | Neural router DUSN-X | SFT LLM LoRA Qwen |
|---|---|---|
| 1. Bài toán | Cập nhật recurrent state, dự đoán intent/agent/action theo event và time gap | Sinh câu trả lời tiếng Việt từ context có thẩm quyền; không thực thi CRUD |
| 2. Dữ liệu | Colab metadata: 4185 train event/371 chuỗi, 203 validation event/46 chuỗi; synthetic legacy có lặp cao | 43 train/49 assistant pairs, 12 validation/12 pairs; test hiện 8 case đã khóa riêng |
| 3. Tiền xử lý | Encode event/text/platform/time; feedback của event trước; windows theo chuỗi | Chat template Qwen, exact tokenizer revision pin, completion-only mask, max_length512 |
| 4. Đặc trưng/phân tích | Global/platform/task vectors 160/112/112; không phải văn bản memory trong DB | Prompt/context và active/obsolete/clarification contracts; audit duplicate/near-duplicate |
| 5. Chia/chọn model | Split theo chuỗi/user/template family; checkpoint compatibility schema/vocab | Base Qwen2.5-0.5B-Instruct revision7ae5576…, LoRA r8/alpha16/dropout0.05; không tune theo test |
| 6. Huấn luyện | Artifact Colab Run01, best epoch6, 3814/157 windows; Tuần4 không train lại | Manifest người dùng cung cấp: pretrained_instruct_lora_sft, T4, epochs3, checkpoint21, training_complete; Tuần4 chỉ kiểm artifact |
| 7. Đánh giá/triển khai | Validation mean Macro-F1≈0.8062 là routing; native checkpoint hash56f56e…; không kết luận hơn baseline | Base/candidate transport8/8 mỗi model; automatic và nội dung AI tách riêng; không promote, cần human review độc lập |

Nguồn router: [CHECKPOINT_COLAB_RUN_01](CHECKPOINT_COLAB_RUN_01.md).
Nguồn LLM đã loại dữ liệu riêng: [evaluation-01](evidence/llm-sft/evaluation-01/README.md).
Số epoch/checkpoint lấy từ manifest artifact, không phải agent tự chạy Colab.
Manifest resume cuối có `train_loss=0.0`, runtime cực ngắn: không dùng số này như
loss huấn luyện đầy đủ hoặc chứng minh chất lượng. Chưa có đủ log gốc từng epoch
trong gói export để vẽ learning curve đáng tin cậy.

Loss/token accuracy đo mục tiêu tối ưu/ngôn ngữ token; Macro-F1 đo phân loại routing;
rubric content đo câu trả lời. Không gộp thành một “độ chính xác AI”. Thống kê windows
khác event; số assistant pairs khác chuỗi. Hidden state vector và SQLite text memory
là hai loại dữ liệu khác nhau. Rules/template không được gán thành năng lực neural.

Pair cũ là endpoint evaluation với context được cấp, không đo retrieval/router/CRUD.
Nghiệm thu Tuần4 là kiểm correctness/integration riêng, không dùng để sửa gold/test
hoặc chứng minh candidate vượt base. Holdout v3 chưa chạy trong tác vụ; attestation
có sẵn không được tạo/chỉnh sửa. Điểm AI tạm thời người dùng nêu 4/8 candidate,
3/8 base chưa có gói review gốc được tìm thấy, nên không biến thành human review.
