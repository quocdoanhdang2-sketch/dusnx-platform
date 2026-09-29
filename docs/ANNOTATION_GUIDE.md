# Hướng Dẫn Thẩm Định Nhãn Độc Lập (Blind Annotation Guide)

Reviewer chỉ nhận bản xuất mù (blind) không lộ đáp án và đọc toàn bộ chuỗi theo thứ tự thời gian. Tuyệt đối **không mở `predictions.jsonl`, `errors.json`, `gold_state` hoặc báo cáo model trước khi chốt nhãn**.

---

## 1. Gói Dữ Liệu Dành Cho Reviewer (Blind Packages)

Chúng tôi đã chuẩn bị sẵn gói duyệt nhãn độc lập:
- **Holdout v2 Blind Package:**
  - File bảng tính CSV: `runtime/reviewer_package/holdout_v2_blind_template.csv` (38 dòng).
  - File JSONL tương đương: `runtime/reviewer_package/holdout_v2_blind_template.jsonl`.
- **Holdout v3 Blind Package (Mới, khóa độc lập):**
  - File bảng tính CSV: `runtime/reviewer_package/holdout_v3_blind_template.csv` (311 dòng).
  - File JSONL tương đương: `runtime/reviewer_package/holdout_v3_blind_template.jsonl`.

### Quy tắc bảo vệ Blind Template (Blind Safeguards):
1. Toàn bộ các trường `gold_*`, `expected_*`, `predictions`, `keywords`, và `labels` trong file blind đều được đặt là `null` hoặc để trống.
2. Tuyệt đối **không dùng file blind template làm gold trong lệnh so sánh hoặc phân xử**. Hệ thống có bộ kiểm tra tự động (`is_blind_template`), sẽ chặn ngay lập tức nếu phát hiện file blind chưa điền nhãn được truyền vào `--compare-with` hoặc `--gold`.

### Quy trình giao việc cho Reviewer:
1. Gửi file `.csv` trong `runtime/reviewer_package/` cho Reviewer (người độc lập với tác giả prompt/code).
2. Reviewer mở file (bằng Excel, LibreOffice hoặc Google Sheets) và điền vào các cột:
   - `label_intent`: Chọn trong 6 intent (`chat`, `research`, `summarize`, `presentation_edit`, `recommendation`, `followup`) hoặc intent trí nhớ (`memory_create`, `decision_modify_intent`, `decision_update`, `decision_update_cancelled`).
   - `label_agent`: Chọn (`conversation`, `search_rag`, `productivity`, `memory`).
   - `label_action`: Chọn (`reply`, `search`, `summarize`, `edit_slide`, `recommend`, `clarify`, `create_memory`, `await_confirm`, `update_memory`, `no_op`).
   - `label_requires_clarification`: Điền `true` nếu câu mơ hồ/thiếu ngữ cảnh cần hỏi lại trước khi thực hiện; điền `false` nếu rõ nghĩa.
   - `label_active`: Danh sách các sự thật/quyết định còn hiệu lực sau lượt này (phân cách bằng dấu phẩy).
   - `label_obsolete`: Danh sách các thông tin cũ đã bị thay thế hoặc hủy bỏ sau lượt này.
   - `notes`: Ghi chú lý giải ngắn gọn, đặc biệt nếu câu mang tính phủ định, đổi ý, từ chối hoặc nhắc đến tin đồn chưa xác nhận.
3. Reviewer **giữ nguyên thứ tự các dòng và các cột định danh** (`record_id`, `sequence_id`, `step`, `platform`, `session_id`, `user_message`).

---

## 2. Tiêu Chí Gán Nhãn Nghiên Cứu

- **`active` (Thông tin còn hiệu lực):** Sự thật hoặc quyết định người dùng đã xác nhận rõ ràng, còn giá trị sử dụng sau lượt hiện tại. Câu hỏi nghi vấn, giả thuyết hoặc "nghe nói trên mạng" KHÔNG tạo thành quyết định active.
- **`obsolete` (Thông tin lỗi thời):** Thông tin cũ đã bị thay thế bởi một quyết định mới có xác nhận. Một đề xuất đổi ý nhưng sau đó người dùng từ chối xác nhận thì thông tin cũ vẫn là `active`, không bị thành `obsolete`.
- **`intent` (Mục đích bước):** Dựa hoàn toàn vào câu nói của người dùng và ngữ cảnh hội thoại đã diễn ra trước đó. Tuyệt đối không nhìn vào feedback hoặc câu trả lời ở tương lai.
- **`requires_clarification`:** Là `true` khi người dùng yêu cầu sửa đổi mà hệ thống đang có nhiều hơn 1 thông tin tương tự (ví dụ: đang dùng cả RabbitMQ và Kafka, người dùng nói "đổi message queue" mà không nói đổi cái nào) hoặc yêu cầu thiếu tham số trọng yếu.

---

## 3. Các Lệnh PowerShell Xử Lý & Đối Soát Nhãn (CLI Commands)

Toàn bộ quy trình được thực hiện qua script `python/scripts/review_labels.py`:

```powershell
# Thiết lập PYTHONPATH (PowerShell)
$env:PYTHONPATH="python/src;python"

# 1. Xuất template blind từ file benchmark gold gốc
python python/scripts/review_labels.py --input benchmarks/holdout_v2.jsonl --output runtime/reviewer_package/holdout_v2_blind_template.jsonl --blind
python python/scripts/review_labels.py --input runtime/reviewer_package/holdout_v2_blind_template.jsonl --output runtime/reviewer_package/holdout_v2_blind_template.csv --to-csv

# 2. Reviewer điền xong file CSV, chuyển đổi CSV về JSONL
python python/scripts/review_labels.py --input runtime/reviewer_submission.csv --output runtime/reviewer_submission.jsonl --from-csv

# 3. Kiểm tra tính hợp lệ của bài nộp (schema validation: đúng kiểu, đủ trường, thuộc danh mục hợp lệ)
python python/scripts/review_labels.py --input runtime/reviewer_submission.jsonl --validate

# 4. So sánh bài nộp của Reviewer với file Gold gốc được giữ kín (xuất Cohen's Kappa và danh sách bất đồng)
python python/scripts/review_labels.py --input runtime/reviewer_submission.jsonl --gold benchmarks/holdout_v2.jsonl --output runtime/agreement_report.json

# 5. Phân xử (Adjudication) chính thức để chốt benchmark đã duyệt
python python/scripts/review_labels.py --input runtime/reviewer_submission.jsonl --gold benchmarks/holdout_v2.jsonl --adjudicate --adjudicator "TenNguoiThamDinh" --output runtime/adjudicated_benchmark.json

# Lưu ý: Nếu chạy thử nghiệm bằng dữ liệu giả định/mock, kết quả sẽ tự động mang trạng thái "test_only_synthetic_adjudication".
# Không bao giờ tự ý sửa trạng thái thành human_reviewed nếu không có sự tham gia của con người thật.
```

---

## 4. Tình Trạng Các Tập Đánh Giá (Benchmark Status)

- **Holdout v1 (8 chuỗi / 29 bước, SHA-256 `34e622b7...`):** Đã được dùng trong vòng phát triển và chẩn đoán trước; phân loại là **Development / Diagnostic Set**.
- **Holdout v2 (10 chuỗi / 38 bước, SHA-256 `1dfd8f1b...`):** Đã chạy đánh giá và xem kết quả chẩn đoán; phân loại là **Diagnostic Set**. Trạng thái nhãn: `review_status: not_independently_reviewed`.
- **Holdout v3 (20 chuỗi / 311 bước, SHA-256 `094268aaf47fa5328786846aff46ebe2f271fd05e2633e681fee472adc8e71bd`):**
  - Tập đánh giá độc lập hoàn toàn mới, bao gồm các chuỗi dài 15–30 lượt, đổi phiên, chuyển đổi Web ↔ PowerPoint, hai trí nhớ cùng loại, câu thiếu chủ ngữ, và không lặp từ khóa.
  - Phân loại: **Prone/Unseen Locked Benchmark**.
  - **QUY TẮC BẤT DI BẤT DỊCH:** Tuyệt đối KHÔNG chạy model, baseline, rule hay prediction nào trên `holdout_v3` cho đến khi nhãn được người độc lập thẩm định xong và model được chốt.
- **Duyệt mapping MASSIVE vi-VN:** Đọc `runtime/external-data/massive/inspection.json`, xem các ví dụ cụ thể của từng intent, ghi nhận xét và đổi `review_status: approved` cùng tên reviewer trong `configs/massive_vi_mapping.json`. Khi chưa duyệt, toàn bộ dữ liệu MASSIVE bị loại khỏi tập train.
