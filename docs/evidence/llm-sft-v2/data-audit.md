# LLM SFT v2 data audit

- Dữ liệu: AI-generated, `needs_human_review`, CC0-1.0; không được gắn human-reviewed.
- Train: 100 sequences / 100 assistant pairs; validation: 24/24; test draft: 16/16.
- VI/EN cân bằng theo lượt. Validator kiểm `response_language`, PII/secret, thứ tự role,
  future/forbidden fact, clarification question, exact prompt/identity/scenario leakage.
- Exact duplicate prompt: 0 trong từng split. Không có ID, sequence, user hoặc scenario family
  trùng giữa split.
- Audit near-duplicate ở ngưỡng 0.98 không thấy cặp cross-split; max cross-split similarity
  đo được 0.9689. Nhiều cặp cùng split vượt 0.98 do generator dùng khung câu lặp.
- Tokenizer exact chưa chạy vì đây là draft và chưa pin tokenizer revision cho v2.
- Manifest giữ `locked=false`, `training_allowed=false`, `official_evaluation_allowed=false`.

Kết luận: cấu trúc và provenance đạt cho development draft; độ đa dạng chưa đạt data gate để
full train. Cần human rewrite/review và audit lại ở ngưỡng 0.82 trước khi khóa test.
