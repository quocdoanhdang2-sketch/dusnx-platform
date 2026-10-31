# Kiểm kê tích hợp và phần còn thiếu

Phạm vi: mã trong checkout cloud `121d946` và patch đang bàn giao; không truy cập
tenant/OA/dịch vụ trả phí hay gửi tin nhắn ra ngoài. Không có secret binding của
Teams/Zalo/image provider trong cấu hình instance; các biến ứng dụng tương ứng cũng
không được inject. Không yêu cầu gửi secret vào chat.

| Thành phần | Có trong repo | Bằng chứng hiện tại |
|---|---|---|
| Web | Web tĩnh, Gateway auth/chat/memory/project | HTTP và Chromium local thật |
| PowerPoint | Office.js task pane, manifest, proposal/Apply | Office mock; HTTPS local/CORS thật; chưa Desktop |
| Word | Chưa thấy add-in riêng hoặc Word.run | Chỉ kiểm kê mã; chưa triển khai |
| Teams | Chưa thấy bot/adapter/manifest Teams | Chỉ kiểm kê mã; chưa có tenant credential |
| Zalo | /webhooks/zalo, normalized payload, channel worker, dedupe local | HTTP local khi chưa cấu hình bị 503; chưa OA thật |
| Ảnh | Text provider Ollama/OpenAI-compatible | Không có vision/image-edit adapter; chưa chỉnh ảnh |

## Word: tích hợp tối thiểu, chưa viết backend mới

Tạo manifest/task pane Office.js riêng sau khi có Word Desktop và HTTPS được tin cậy.
Dùng lại Gateway `/v1/auth/*`, `/v1/sessions`, `/v1/chat`, `/v1/memories` và
`/v1/me/events`; token opaque chỉ trong RAM. Không nhận user_id tự khai làm danh tính.
Chỉ gửi đoạn văn đang chọn và lệnh người dùng; không gửi toàn tài liệu mặc định.
Proposal phải tách khỏi tài liệu; trước Apply kiểm tra tài liệu/range/text gốc vẫn
khớp, từ chối selection đã đổi, kết quả rỗng/metadata/không đổi hoặc provider lỗi.
Người dùng review rồi chủ động Apply; không tự ghi tài liệu.

Cần xác định Office requirement set, hành vi range tracking và chính sách thông tin
nhạy cảm trước khi code. Acceptance: đăng nhập chung, memory isolation, nguồn trả
lời đúng, selection/text change guard, undo và thử trực tiếp trên Word Desktop.
Harness không thay bằng chứng Desktop.

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
