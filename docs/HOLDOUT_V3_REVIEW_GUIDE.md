# Duyệt độc lập holdout v3 trên Windows

Trạng thái: **chưa có reviewer thật nộp nhãn; chưa đánh giá v3 trong nhiệm vụ này**. Chỉ kiểm tra SHA-256 và manifest, cùng tính mù của package: 311 lượt / 20 chuỗi, hash `094268aaf47fa5328786846aff46ebe2f271fd05e2633e681fee472adc8e71bd`. Không chạy model, rule, baseline hoặc scorer trước review.

## 1. Tìm file và chuẩn bị gửi

Mở PowerShell:

```powershell
Set-Location D:\Projects\dusnx-platform
$py = '.\python\.venv\Scripts\python.exe'
$env:PYTHONPATH='python/src;python;.;scripts'
Get-Item runtime\reviewer_package\holdout_v3_blind_template.csv
Get-Item runtime\reviewer_package\holdout_v3_blind_template.jsonl
& $py python/scripts/audit_review_package.py --benchmark benchmarks/holdout_v3.jsonl --manifest benchmarks/holdout_v3.manifest.json --jsonl runtime/reviewer_package/holdout_v3_blind_template.jsonl --csv runtime/reviewer_package/holdout_v3_blind_template.csv
$package = Join-Path $PWD 'runtime\reviewer_send_v3'
New-Item -ItemType Directory -Path $package -ErrorAction Stop
Copy-Item -LiteralPath runtime\reviewer_package\holdout_v3_blind_template.csv -Destination $package
Copy-Item -LiteralPath docs\HOLDOUT_V3_REVIEW_GUIDE.md -Destination $package
explorer.exe $package
```

Nếu thư mục tồn tại, chọn tên mới; không ghi đè bài nộp. **Chỉ tự gửi CSV blind và hướng dẫn** trong thư mục này. Không gửi repo, gold, predictions, error report, checkpoint hoặc ghi chú đáp án. Agent không gửi file cho ai. JSONL blind dùng làm bản đối chiếu máy. ID gốc chỉ phục vụ ghép lượt; package không có gold/expected/prediction và notes đều trống.

## 2. Người duyệt điền và nộp

Excel: **Data → From Text/CSV → UTF-8**; hoặc LibreOffice. Đọc toàn bộ từng chuỗi theo step/session/platform. Không xem prediction hoặc dùng model gán nhãn. Giữ nguyên record_id, sequence_id, step, platform, session_id, user_message và thứ tự dòng.

| Cột điền | Quy tắc |
|---|---|
| reviewer | Tên/mã người thật |
| review_date | Ngày ISO YYYY-MM-DD (timestamp ISO cũng được) |
| label_active | JSON array sự thật đã xác nhận, còn hiệu lực sau lượt; không có thì **[]**, không để trống |
| label_obsolete | JSON array sự thật bị thay thế; không có thì **[]** |
| label_intent | chat, research, summarize, presentation_edit, recommendation, followup, memory_create, decision_modify_intent, decision_update, decision_update_cancelled, clarify_missing_context, clarify_ambiguous_decision |
| label_agent | conversation, search_rag, productivity, memory |
| label_action | reply, search, summarize, edit_slide, recommend, clarify, create_memory, await_confirm, update_memory, no_op |
| label_requires_clarification | true hoặc false |
| notes | Lý do do reviewer tự viết nếu cần |

Ví dụ định dạng (không phải đáp án v3): `["Một sự thật có dấu phẩy, vẫn là một phần tử"]`. JSON array tránh tách nhầm câu; danh sách đơn giản ngăn bằng dấu phẩy vẫn được hỗ trợ. Ô trống là chưa duyệt, khác [] là xác nhận không có fact.

Active không đổi khi chỉ hỏi, nghe đồn hoặc đề nghị đổi chưa xác nhận. Chỉ xác nhận mới supersede; từ chối giữ quyết định cũ. Thiếu bối cảnh hoặc nhiều đối tượng phù hợp thì hỏi rõ. Đổi phiên không xóa memory; đổi chủ đề không tự tạo quyết định. Không dùng lượt tương lai để gán nhãn hiện tại.

Core route: chat→conversation/reply; research→search_rag/search; summarize→productivity/summarize; presentation_edit→productivity/edit_slide; recommendation→conversation/recommend. Followup cần xét ngữ cảnh, không mặc định clarify. Memory CRUD/confirm là **logic ứng dụng**, không phải neural router. Nhãn chưa phù hợp schema thì ghi notes để điều phối, không sửa câu gốc.

Lưu riêng `holdout_v3_reviewed_A.csv` bằng **CSV UTF-8** và nộp người điều phối. Không đổi tên blind chưa điền thành gold.

## 3. Kiểm tra bài nộp thật

Đặt bài nộp trong runtime/reviews/, không commit:

```powershell
& $py python/scripts/review_labels.py --input runtime/reviews/holdout_v3_reviewed_A.csv --validate --template runtime/reviewer_package/holdout_v3_blind_template.jsonl
& $py python/scripts/review_labels.py --input runtime/reviews/holdout_v3_reviewed_A.csv --from-csv --output runtime/reviews/reviewer_A.jsonl
```

Mong đợi `Valid review file: 311 records...`. Bắt buộc dùng **--template** để bắt thiếu/thừa dòng, sai ID/thứ tự và sửa input; --validate đơn lẻ không kiểm tra đủ 311 dòng. Nhãn thiếu/sai, ngày sai và gold dùng nhầm làm submission bị từ chối.

## 4. Agreement và phân xử — chưa chạy trên v3 lúc này

Chỉ sau khi có bài thật hợp lệ, người điều phối có thể so reviewer với gold gốc:

```powershell
& $py python/scripts/review_labels.py --input runtime/reviews/reviewer_A.jsonl --gold benchmarks/holdout_v3.jsonl --output runtime/reviews/agreement.json
& $py python/scripts/review_labels.py --input runtime/reviews/reviewer_A.jsonl --gold benchmarks/holdout_v3.jsonl --adjudicate --adjudicator 'TEN_NGUOI_PHAN_XU_THAT' --output runtime/reviews/adjudication-draft.json
```

Có reviewer B độc lập thì validate tương tự và thay --gold bằng `--compare-with runtime/reviews/reviewer_B.jsonl`. Report chứa agreement, Cohen's kappa cho intent/agent/action/clarification, set agreement active/obsolete và từng bất đồng. Kappa null khi không có biến thiên lớp. So reviewer với nhãn authored gốc không tương đương hai reviewer độc lập.

Người thật đọc context và phân xử, tạo `runtime/reviews/resolutions.json`:

```json
{"RECORD_ID": {"intent": {"resolved_value": "chat", "reason": "Lý do được người thật thống nhất"}}}
```

Chạy lại lệnh adjudicate thêm `--resolutions runtime/reviews/resolutions.json`, đổi output thành `runtime/reviews/adjudication-final.json`. Đây là **JSON audit**, không phải JSONL benchmark. Bản nháp luôn là `draft_pending_human_attestation`; nhập tên không tự biến thành human_reviewed. Phải giải quyết hết PENDING_HUMAN_RESOLUTION.

## 5. Khóa sau review và phân xử thật

Chỉ người điều phối đã xác nhận quy trình review thật chạy:

```powershell
& $py python/scripts/lock_review.py --adjudication runtime/reviews/adjudication-final.json --reviewer-a runtime/reviews/reviewer_A.jsonl --reviewer-b benchmarks/holdout_v3.jsonl --gold-reference --template runtime/reviewer_package/holdout_v3_blind_template.jsonl --output runtime/reviews/holdout_v3_reviewed_labels.jsonl --attest-human-review
Get-FileHash runtime/reviews/holdout_v3_reviewed_labels.jsonl -Algorithm SHA256
```

Với hai reviewer thật, bỏ --gold-reference và đặt reviewer-b về reviewer_B.jsonl. Công cụ tạo file nhãn mới và manifest hash/audit, trạng thái `operator_attested_human_review`: lời xác nhận của người vận hành, không phải công cụ tự xác minh danh tính. Không ghi đè gold/manifest gốc, không chạy đánh giá. Giữ bài nộp và bằng chứng review riêng; không commit thông tin reviewer.

## 6. Kế hoạch sau review, chưa thực hiện

Khóa nhãn/hash → cố định checkpoint SHA và commit code → tích hợp nhãn phân xử vào bản benchmark reviewed có audit → kiểm tra schema/hash → **một vòng đánh giá v3** baseline/no-state/full. Báo mọi lỗi, current recall, obsolete, clarification, macro-F1 từng head, final answer; khoảng tin cậy bootstrap theo **sequence**, không coi 311 lượt độc lập. Tách template/application rules khỏi neural router; no-state giữ cùng logic ứng dụng. Sau đó mới quyết định thu thập thêm dữ liệu/train lại. V3 đã mở kết quả sẽ trở thành tập đã xem; không tái dùng như holdout mù cho model sửa theo lỗi v3.
