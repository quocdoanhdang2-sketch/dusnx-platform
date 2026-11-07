# Kiểm kê tích hợp và phần còn thiếu

Phạm vi: mã trong checkout cloud `121d946` và patch đang bàn giao; không truy cập
tenant/OA/dịch vụ trả phí hay gửi tin nhắn ra ngoài. Không có secret binding của
Teams/Zalo/image provider trong cấu hình instance; các biến ứng dụng tương ứng cũng
không được inject. Không yêu cầu gửi secret vào chat.

| Thành phần | Có trong repo | Bằng chứng hiện tại |
|---|---|---|
| Web | Web tĩnh, Gateway auth/chat/memory/project | HTTP và Chromium local thật |
| PowerPoint | Office.js task pane, manifest, proposal/Apply, sửa text và sinh slide từ template | PowerPoint Desktop thật, PowerPointApi 1.5; xem `docs/evidence/powerpoint-addin-generate-20261107` |
| Word | Office.js task pane, manifest, proposal/Apply, guard selection | Word Desktop thật, WordApi 1.1; xem `docs/evidence/word-addin-desktop-20261106` |
| Teams | Chưa thấy bot/adapter/manifest Teams | Chỉ kiểm kê mã; chưa có tenant credential |
| Zalo | /webhooks/zalo, normalized payload, channel worker, dedupe local | HTTP local khi chưa cấu hình bị 503; chưa OA thật |
| Ảnh | Text provider Ollama/OpenAI-compatible | Không có vision/image-edit adapter; chưa chỉnh ảnh |

## Word: task pane Office.js đã chạy trên Word Desktop

Đã triển khai `word-addin/` dùng lại Gateway `/v1/auth/*`, `/v1/sessions`, `/v1/chat`; token
opaque chỉ trong RAM. Chỉ gửi đoạn đang chọn và instruction, không gửi toàn tài liệu.
Proposal tách khỏi tài liệu; trước Apply kiểm tra lại text/start/end, session và trạng thái
đăng nhập, từ chối selection đã đổi, kết quả rỗng/metadata/không đổi hoặc thiếu provenance
LLM thực. Người dùng chủ động Apply; paragraph break cuối được giữ.

Đã kiểm chứng trên Microsoft Word 16.0.20527.20112 (WordApi 1.1/1.3): task pane nạp qua HTTPS
local, đăng nhập, proposal + provenance `response_source: "llm"`, Apply đúng một lần, guard từ
chối khi đổi selection và tài liệu không đổi. Bằng chứng và ảnh chụp:
`docs/evidence/word-addin-desktop-20261106`. Runbook: `docs/WORD_ADDIN_RUNBOOK.md`.

Còn thiếu trước production: manifest đã ký/central deployment thay vì sideload registry; HTTPS
cùng origin cho WebView2 (dev đã chạy `word-addin/dev-server.js` proxy `/v1/*`; production cần
reverse proxy và CA nội bộ thay certificate localhost); chính sách dữ liệu nhạy cảm và retention;
xử lý bảng/field/tracked changes; undo/telemetry; và model chất lượng cao hơn (mỗi máy tự chọn
Qwen2.5 theo VRAM, hoặc ép qua `DUSNX_OLLAMA_MODEL`/`DUSNX_MODEL_PROFILE`; bằng chứng hiện tại
dùng `qwen2.5:1.5b-instruct`, chưa đủ ổn định để coi nội dung là bản cuối). Harness mock không
thay bằng chứng Desktop.

## PowerPoint: hai mode đã chạy trên Desktop

`powerpoint-addin/` có hai mode dùng chung `/v1/chat`, token opaque trong RAM:

- **Edit selected text** đọc đúng một slide + một text shape, hiện proposal/provenance và
  chỉ ghi khi Apply; guard từ chối đổi slide/shape/text/session hoặc mất login.
- **Generate slides from instruction** nhận outline chặt (1–6 slide, 1–5 bullet), hiện preview,
  rồi chèn N slide từ `deck-template.pptx` sau slide cuối với đúng title/body/footer. Template
  tải same-origin; lỗi chèn sẽ rollback các slide vừa thêm.

Đã kiểm chứng trên Microsoft PowerPoint `16.0.20527`: sinh 3 slide vào deck trống, append 3
slide sau slide 3 giữ thứ tự (footer tuyệt đối 4–6), và sửa `DUSN-X Body` tại chỗ. Bằng chứng:
`docs/evidence/powerpoint-addin-generate-20261107`. Runbook: `docs/POWERPOINT_ADDIN_RUNBOOK.md`.

Còn thiếu trước production: manifest ký/central deployment; lưu deck bàn giao và kiểm Undo/Redo;
nhiều cửa sổ PowerPoint; model local chưa ổn định định dạng outline nên preview là bắt buộc;
HTTPS production/reverse proxy và CA nội bộ; chính sách dữ liệu nhạy cảm. Bằng chứng sinh slide
dùng candidate `dusnx-vi-v3-20261107` để chạy tích hợp, không promote; stack đã khôi phục
`qwen2.5:1.5b-instruct`.

## Teams và Zalo

Teams cần app/bot registration, tenant/App ID, callback HTTPS, cơ chế xác minh JWT
đúng audience/issuer, chống replay và mapping tài khoản có xác thực tới user DUSN-X.
Không tin platformUserId từ payload để truy cập SQLite memory. Credential chỉ nhập
secret store/environment settings, giới hạn đích HTTPS. Cần policy tenant/admin
consent, tài khoản test, retention và log redaction trước thử bot thật.

Zalo hiện là **normalized webhook skeleton** với header X-DUSNX-Webhook-Secret,
không phải bộ xác minh chữ ký OA chính thức và không chứng minh OA đã kết nối.
Patch từ chối khi secret chưa cấu hình; không điền secret mặc định để bật.
Cần OA/app quyền hợp lệ, token lưu an toàn, callback HTTPS, signature/timestamp/replay
theo hợp đồng Zalo thực tế, mapping tài khoản và kiểm thử sandbox trước khi bật gửi.
Channel/dedupe trong RAM chưa đảm bảo bền khi restart; lỗi callback cần được thiết kế
retry/idempotency trước production. Không gửi tin thật trong đợt này.

## Vision và chỉnh ảnh

Qwen text hiện tại không phải vision hoặc image-edit model. Chưa có provider nên
không tạo nút/chức năng Apply ảnh giả. Trước triển khai cần:

1. Chọn provider/model có image input + edit thực; kiểm quyền dùng và vùng dữ liệu.
2. Cấu hình destination allowlist, secret store, timeouts, MIME/size/pixel limit,
   ngân sách/quota. Không đưa API key vào task pane hoặc source.
3. Thống nhất consent cho ảnh/tài liệu, thời gian lưu, xóa file và chống truy cập chéo user.
4. Lưu bản gốc; preview ảnh mới; người dùng review rồi Apply vào đúng mục tiêu đã chọn.
5. Kiểm thử ảnh thật được phép dùng, prompt injection/metadata, lỗi API/quota/timeout,
   đổi selection khi chờ và rollback/undo.

Chi phí chưa có số liệu vì chưa chọn nhà cung cấp: phải tính theo model, resolution,
số lần edit, storage/egress và concurrency. Cần người dùng chọn provider/ngân sách,
nhập credential an toàn và cấp ảnh test trước khi kết luận tích hợp chạy được.
