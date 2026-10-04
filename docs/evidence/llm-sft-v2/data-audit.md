# LLM SFT v2 data audit

- Dữ liệu: AI-generated, `needs_human_review`, CC0-1.0; không được gắn human-reviewed.
- Train: 100 sequences / 100 assistant pairs; validation: 24/24; test draft: 16/16.
- VI/EN cân bằng theo lượt. Validator kiểm `response_language`, PII/secret, thứ tự role,
  future/forbidden fact, clarification question, exact prompt/identity/scenario leakage.
- Exact duplicate prompt: 0 trong từng split. Không có ID, sequence, user hoặc scenario family
  trùng giữa split.
- Bản draft ban đầu có 2.028 cặp cross-split ở ngưỡng 0.82, bao phủ toàn bộ 140 record;
  max cross-split similarity là 0.9689. Nguyên nhân là mọi scenario family dùng chung một
  mẫu `current decision / no confirmed decision`, chỉ thay marker và topic.
- Generator draft-03 tạo nội dung đúng với 12 scenario family, dùng khung tường thuật khác
  nhau cho các lần lặp và dịch khung giữa train/validation/test draft. Audit máy sau sửa không
  còn cặp cross-split hoặc within-split ở ngưỡng 0.82; max cross-split similarity là 0.8157.
- `rewrite_queue.csv` hiện rỗng ở ngưỡng 0.82. Đây chỉ là diversity gate bằng máy; nó không
  biến record thành `human_reviewed` và không thay thế việc người thật đọc nội dung.
- Tokenizer exact chưa chạy vì đây là draft và chưa pin tokenizer revision cho v2.
- Manifest giữ `locked=false`, `training_allowed=false`, `official_evaluation_allowed=false`.

Kết luận: diversity gate ở ngưỡng 0.82 đã đạt cho cả trong và giữa các split. Human content
review vẫn chưa đạt data gate. Manifest tiếp tục khóa full train và official evaluation cho đến
khi có review receipt hợp lệ và một `test.jsonl` độc lập do người thật viết/duyệt trước prediction.
