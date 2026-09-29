# Hướng Dẫn Thẩm Định Nhãn Độc Lập (Blind Annotation Guide)

Reviewer chỉ nhận bản xuất không lộ đáp án và đọc toàn bộ chuỗi theo thứ tự thời gian. Tuyệt đối **không mở `predictions.jsonl`, `errors.json`, `gold_state` hoặc báo cáo model trước khi chốt nhãn**.

---

## 1. Gói Dữ Liệu Dành Cho Reviewer (Blind Template)

Chúng tôi đã chuẩn bị sẵn gói duyệt nhãn độc lập cho tập benchmark khóa mới `holdout_v2`:
- File bảng tính CSV: `runtime/reviewer_package/holdout_v2_blind_template.csv` (38 dòng, dễ mở bằng Microsoft Excel, LibreOffice hoặc Google Sheets).
- File JSONL tương đương: `runtime/reviewer_package/holdout_v2_blind_template.jsonl`.

### Quy trình giao việc:
1. Gửi file `runtime/reviewer_package/holdout_v2_blind_template.csv` cho Reviewer 2 (người độc lập với tác giả prompt/code).
2. Reviewer mở file và điền vào các cột:
   - `suggested_intent`: Chọn trong danh mục 6 intent (`chat`, `research`, `summarize`, `presentation_edit`, `recommendation`, `followup`) hoặc intent trí nhớ (`memory_create`, `decision_modify_intent`).
   - `suggested_agent`: Chọn (`conversation`, `search_rag`, `productivity`, `memory`).
   - `suggested_action`: Chọn (`reply`, `search`, `summarize`, `edit_slide`, `recommend`, `clarify`, `create_memory`, `await_confirm`, `update_memory`, `no_op`).
   - `suggested_clarification`: Điền `true` nếu câu mơ hồ, cần hỏi lại trước khi làm; điền `false` nếu rõ nghĩa.
   - `notes`: Ghi chú lý giải ngắn gọn, đặc biệt nếu câu mang tính phủ định, đổi ý, từ chối hoặc nhắc đến tin đồn chưa xác nhận.
3. Reviewer **giữ nguyên thứ tự các dòng và các cột định danh** (`record_id`, `sequence_id`, `step`, `platform`, `user_message`, `session_id`, `project_id`).

---

## 2. Tiêu Chí Gán Nhãn Nghiên Cứu

- **`active` (Thông tin còn hiệu lực):** Sự thật hoặc quyết định người dùng đã xác nhận rõ ràng, còn giá trị sử dụng sau lượt hiện tại. Câu hỏi nghi vấn, giả thuyết hoặc "nghe nói trên mạng" KHÔNG tạo thành quyết định active.
- **`obsolete` (Thông tin lỗi thời):** Thông tin cũ đã bị thay thế bởi một quyết định mới có xác nhận. Một đề xuất đổi ý nhưng sau đó người dùng từ chối xác nhận thì thông tin cũ vẫn là `active`, không bị thành `obsolete`.
- **`intent` (Mục đích bước):** Dựa hoàn toàn vào câu nói của người dùng và ngữ cảnh hội thoại đã diễn ra trước đó. Tuyệt đối không nhìn vào feedback hoặc câu trả lời ở tương lai.
- **`requires_clarification`:** Là `true` khi người dùng yêu cầu sửa đổi mà hệ thống đang có nhiều hơn 1 thông tin tương tự (ví dụ: đang dùng cả RabbitMQ và Kafka, người dùng nói "đổi message queue" mà không nói đổi cái nào) hoặc yêu cầu thiếu tham số trọng yếu.

---

## 3. Các Lệnh Xử Lý & Đối Soát Nhãn (CLI Commands)

Tất cả thao tác đối soát được thực hiện tự động qua script `python/scripts/review_labels.py`:

```powershell
# 1. Xuất template blind từ bất kỳ benchmark hoặc dataset nào
python python/scripts/review_labels.py --input benchmarks/holdout_v2.jsonl --output runtime/reviewer_package/my_blind.jsonl --blind
python python/scripts/review_labels.py --input runtime/reviewer_package/my_blind.jsonl --output runtime/reviewer_package/my_blind.csv --to-csv

# 2. Chuyển đổi CSV sau khi reviewer hoàn thành về JSONL
python python/scripts/review_labels.py --input reviewer_b_completed.csv --output runtime/reviewer_b.jsonl --from-csv

# 3. Kiểm tra tính toàn vẹn (schema validation: đúng kiểu, đủ trường, thuộc danh mục hợp lệ)
python python/scripts/review_labels.py --input runtime/reviewer_b.jsonl --validate

# 4. Đối chiếu đồng thuận (Inter-Annotator Agreement) & tính Cohen's Kappa giữa 2 reviewer
python python/scripts/review_labels.py --input runtime/reviewer_a.jsonl --compare-with runtime/reviewer_b.jsonl --output runtime/agreement_report.json

# 5. Phân xử (Adjudication) chính thức để chốt benchmark đã duyệt
python python/scripts/review_labels.py --input runtime/reviewer_b.jsonl --adjudicate --adjudicator "NguoiThamDinhChinh" --output benchmarks/holdout_v2.adjudicated.jsonl
```

---

## 4. Tình Trạng Hiện Tại & Cảnh Báo Tính Trung Thực

- **Holdout v1 (8 chuỗi / 29 bước):** Đã bị nhìn thấy và dùng trong vòng chẩn đoán trước; được coi là development set.
- **Holdout v2 (10 chuỗi / 38 bước, SHA-256 `1dfd8f1b...`):** Đã khóa độc lập, thiết kế với các bẫy khó nhưng **hiện tại vẫn mang trạng thái `review_status: not_independently_reviewed`**.
- Tuyệt đối **không tự động gán `human_reviewed=true`** bằng code hoặc AI. Chỉ sau khi Reviewer 2 hoàn tất quy trình và lệnh `--adjudicate` được chạy với chữ ký của người thẩm định thật sự, benchmark mới được ghi nhận là human-reviewed.
- **Duyệt mapping MASSIVE vi-VN:** Đọc `runtime/external-data/massive/inspection.json`, xem các ví dụ cụ thể của từng intent, ghi nhận xét và đổi `review_status: approved` cùng tên reviewer trong `configs/massive_vi_mapping.json`. Khi chưa duyệt, toàn bộ dữ liệu MASSIVE bị loại khỏi tập train.
