# Hướng Dẫn Thao Tác Duyệt Độc Lập Cho Tập Đánh Giá Holdout v3

Tài liệu này cung cấp hướng dẫn từng bước cho **người duyệt độc lập (Independent Reviewer)** tham gia thẩm định nhãn tập dữ liệu `holdout_v3` của dự án DUSN-X.

---

## 1. Nguyên Tắc Cốt Lõi: Đánh Giá Mù (Blind Evaluation)

1. **Không xem trước Gold Labels hay Predictions:**
   - Người duyệt chỉ làm việc với file blind template: `runtime/reviewer_package/holdout_v3_blind_template.csv` (gồm 311 dòng / 20 chuỗi hội thoại).
   - Tuyệt đối **không mở**, **không yêu cầu cung cấp** file `benchmarks/holdout_v3.jsonl` (bản gold đang khóa) hoặc bất kỳ file dự đoán (prediction/error report) nào.
   - Không chạy bất kỳ model hoặc script nào để tự động sinh nhãn thay thế con người.

2. **Tính Trung Thực Về Tình Trạng Review:**
   - Trạng thái hiện tại của `holdout_v3` trong `benchmarks/holdout_v3.manifest.json` là:  
     `"status": "labels_locked_not_independently_reviewed"`
   - **Tuyệt đối không tự sửa thành `human_reviewed`** khi chưa có người thật duyệt và nộp bài hoàn tất.
   - Hệ thống không tự gửi dữ liệu cho người khác thay người dùng.

---

## 2. Các Bước Thao Tác Dành Cho Reviewer

### Bước 1: Tiếp nhận file Blind Template
Reviewer nhận file:
- Đường dẫn: `runtime/reviewer_package/holdout_v3_blind_template.csv`
- Mở bằng bất kỳ phần mềm bảng tính nào (Microsoft Excel, LibreOffice Calc, Google Sheets) với bảng mã UTF-8.

### Bước 2: Hiểu cấu trúc các cột trong CSV
Reviewer cần giữ nguyên 100% các cột định danh hệ thống (KHÔNG sửa, KHÔNG xóa, KHÔNG đổi thứ tự dòng):
- `record_id`: Định danh duy nhất của lượt (ví dụ: `holdout3-20261002-v3_01_cloud_multi_hop_recall-1`).
- `sequence_id`: Mã chuỗi kịch bản.
- `step`: Thứ tự lượt trong chuỗi (bắt đầu từ 1 và tăng dần liên tục).
- `platform`: Nền tảng phát sinh lượt (`web`, `powerpoint`, `zalo`).
- `session_id`: Mã phiên làm việc.
- `user_message`: Câu nói nguyên văn của người dùng trong lượt đó.

### Bước 3: Điền nhãn theo Schema chuẩn
Reviewer điền vào các cột nhãn sau cho từng dòng:

| Cột | Giá trị hợp lệ | Ý nghĩa & Hướng dẫn |
|---|---|---|
| `reviewer` | Tên hoặc mã định danh của bạn (ví dụ: `reviewer_a`) | Ghi nhận người thực hiện. |
| `review_date` | `YYYY-MM-DD` (ví dụ: `2026-10-01`) | Ngày thẩm định. |
| `label_intent` | `chat`, `research`, `summarize`, `presentation_edit`, `recommendation`, `followup`, `memory_create`, `decision_modify_intent`, `decision_update`, `decision_update_cancelled` | Mục đích của câu nói (xem bảng chi tiết bên dưới). |
| `label_agent` | `conversation`, `search_rag`, `productivity`, `memory` | Nhóm tác tử phụ trách. |
| `label_action` | `reply`, `search`, `summarize`, `edit_slide`, `recommend`, `clarify`, `create_memory`, `await_confirm`, `update_memory`, `no_op` | Hành động tiếp theo của hệ thống. |
| `label_requires_clarification` | `true` hoặc `false` | Điền `true` nếu câu mơ hồ/thiếu ngữ cảnh (ví dụ có 2 quyết định cùng loại mà người dùng nói "đổi quyết định" mà không nói đổi cái nào); điền `false` nếu rõ nghĩa. |
| `label_active` | Chuỗi văn bản (hoặc để trống) | Quyết định/sự thật đang có hiệu lực sau lượt này (ví dụ: `PostgreSQL, AWS`). |
| `label_obsolete` | Chuỗi văn bản (hoặc để trống) | Thông tin cũ đã bị thay thế hoặc hủy bỏ sau lượt này (ví dụ: `GCP`). |
| `notes` | Văn bản tự do (tùy chọn) | Ghi chú lý do nếu câu nói có tính phủ định, đổi ý, từ chối hoặc tin đồn chưa xác nhận. |

#### Bảng tra cứu nhanh `label_intent` & `label_agent` & `label_action`:
1. `chat` (`conversation` / `reply`): Chào hỏi, hỏi đáp kiến thức chung, hoặc hỏi lại thông tin đã lưu.
2. `research` (`search_rag` / `search`): Yêu cầu tìm kiếm tài liệu, đối chiếu, kiểm tra nguồn bên ngoài.
3. `summarize` (`productivity` / `summarize`): Yêu cầu tóm tắt tài liệu, rút gọn văn bản đã có sẵn.
4. `presentation_edit` (`productivity` / `edit_slide`): Yêu cầu chỉnh sửa slide, tạo bố cục trình chiếu, sửa speaker notes.
5. `recommendation` (`conversation` / `recommend`): Yêu cầu gợi ý, tư vấn, đưa ra các lựa chọn dựa trên tiêu chí.
6. `followup` (`conversation` / `clarify`): Câu nói tiếp nối ngữ cảnh câu trước hoặc trả lời làm rõ.
7. `memory_create` (`memory` / `create_memory`): Người dùng yêu cầu lưu một thông tin/quyết định mới ("Hãy nhớ rằng...").
8. `decision_modify_intent` (`memory` / `await_confirm`): Người dùng yêu cầu sửa quyết định cũ ("Đổi X sang Y nhé").
9. `decision_update` (`memory` / `update_memory`): Người dùng xác nhận đồng ý áp dụng quyết định mới ("Đồng ý", "Xác nhận").
10. `decision_update_cancelled` (`memory` / `no_op`): Người dùng từ chối cập nhật ("Thôi", "Không đổi nữa").

---

## 3. Kiểm Tra Bài Nộp & Rà Soát Thiếu Sót (Self-Validation)

Trước khi nộp lại file, reviewer (hoặc người điều phối) chạy script kiểm tra định dạng và tính toàn vẹn:

```powershell
# 1. Chuyển đổi file CSV đã điền sang JSONL để kiểm tra
$env:PYTHONPATH="python/src;python"
python python/scripts/review_labels.py --input runtime/reviewer_package/holdout_v3_blind_template.csv --from-csv --output runtime/reviewer_submission.jsonl

# 2. Kiểm tra tính hợp lệ (schema validation)
python python/scripts/review_labels.py --input runtime/reviewer_submission.jsonl --validate
```

**Các lỗi thường gặp script sẽ bắt:**
- Bỏ sót dòng (thiếu `label_intent`, `label_agent`, hoặc `label_action`).
- Sai chính tả giá trị phân loại (ví dụ: gõ `conversation_agent` thay vì `conversation`).
- Định dạng ngày tháng không đúng chuẩn ISO (`YYYY-MM-DD`).

Nếu có lỗi, script sẽ chỉ rõ `record_id` và dòng vi phạm để sửa lại trong CSV.

---

## 4. Quy Trình Nộp Bài & Phân Xử Bất Đồng (Adjudication)

1. **Nộp bài:**
   Reviewer nộp file `holdout_v3_reviewed.csv` cho người phụ trách nghiên cứu.

2. **So sánh với Gold gốc (giữ kín):**
   Người phụ trách chạy lệnh đối soát nhãn giữa Reviewer và bản Gold:
   ```powershell
   python python/scripts/review_labels.py `
     --input runtime/reviewer_submission.jsonl `
     --gold benchmarks/holdout_v3.jsonl `
     --output runtime/holdout_v3_agreement_report.json
   ```
   Lệnh này tính toán:
   - Tỷ lệ đồng thuận thô (Raw Agreement %).
   - Hệ số Cohen's Kappa cho từng nhiệm vụ (Intent, Agent, Action).
   - Danh sách các câu có bất đồng nhãn (disagreements).

3. **Họp phân xử bất đồng (Adjudication):**
   - Với những lượt có bất đồng, Trưởng nhóm thẩm định (Adjudicator) cùng Reviewer xem xét lại ngữ cảnh chuỗi để chốt nhãn đúng theo hợp đồng định nghĩa.
   - Chạy lệnh phân xử để sinh file benchmark hoàn thiện:
     ```powershell
     python python/scripts/review_labels.py `
       --input runtime/reviewer_submission.jsonl `
       --gold benchmarks/holdout_v3.jsonl `
       --adjudicate `
       --adjudicator "TenNguoiPhanXu" `
       --output benchmarks/holdout_v3_adjudicated.jsonl
     ```
   - Khi đó, trạng thái của benchmark mới được chuyển thành `"human_reviewed": true`.

---

## 5. Tóm Tắt Tình Trạng Hiện Tại Của Holdout v3

- **Tập tin:** `benchmarks/holdout_v3.jsonl`
- **SHA-256:** `094268aaf47fa5328786846aff46ebe2f271fd05e2633e681fee472adc8e71bd`
- **Số lượt:** 311 lượt (20 kịch bản chuỗi độc lập).
- **Trạng thái hiện hành:** `labels_locked_not_independently_reviewed` (Chưa qua thẩm định con người độc lập).
- **Cam kết:** Không chạy model đánh giá trước khi hoàn thành quy trình thẩm định độc lập theo hướng dẫn này.
