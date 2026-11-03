# Sửa preference theo scope và reply rỗng sau sanitizer

Baseline: f50c699d3d5600c2cf845cf7a4aa19c60c2f0164.

## Thay đổi

- Khi đọc ngôn ngữ, vẫn cho phép fallback từ project về global.
- Khi ghi, chỉ supersede bản ghi cùng scope với request. Nếu project đang dùng
  fallback global, tạo preference riêng trong project, không thay đổi global.
- Sau sanitizer, response rỗng trở thành lỗi `empty_response`: provider_ok=false,
  giữ provider_called để phản ánh transport đã được gọi, model/token thành null.
  API xử lý qua nhánh provider_error hiện có, không lưu assistant message lỗi.

## Regression

`python/tests/test_scope_and_empty_reply.py` có 11 case:
- HTTP/FastAPI trên DB tổng hợp: global và hai project, fallback read, cập nhật
  trong scope, đổi global không đè project, không tạo bản mới cho giá trị giữ nguyên.
- Ollama/OpenAI với transport mô phỏng: heading bị sanitizer xóa hoặc whitespace
  không được coi thành công.
- HTTP/API với cả hai provider mô phỏng: không lưu reply rỗng; retry cùng request ID
  với response hợp lệ tạo một user message và một assistant message.

Đây là kiểm thử correctness/fault injection, không phải generation live trên Windows.
Không train, sửa model hoặc sửa dữ liệu cá nhân.

## Prompt cho Codex/Antigravity trên Windows

```text
Tích hợp bản sửa scope preference và empty_response mới nhất trên GitHub main,
sau khi đối chiếu local work và remote SHA. Đọc AGENTS.md và file này. Không reset,
clean, force-push hoặc pop stash tự động; bảo toàn DB/checkpoint và sửa cá nhân.

Chạy python/tests/test_scope_and_empty_reply.py trên đúng source mới; sau đó full
pytest, Node Web/auth/Office mock và các harness liên quan. Dùng DB tổng hợp riêng.
Kiểm tra qua API rằng đổi ngôn ngữ ở project A không thay global hoặc project B;
đổi global không ghi đè preference project. Request vi/en rõ ràng vẫn ưu tiên đúng.

Kiểm tra reply bị sanitizer xóa hết: provider_error, provider_ok=false, giữ đúng
provider_called, không lưu assistant lỗi. Retry request ID cũ phải không trùng
message. Phân biệt fault injection với generation thật trong báo cáo.

Trên Windows có model thật, chạy verify_chat_provenance.py và bộ song ngữ với
--strict-language --strict-quality ở output-dir mới. Kiểm tra cả raw output và
output sau sanitizer bằng dữ liệu tổng hợp; không che lỗi bằng cách lọc output
rồi gọi đó là raw generation. Không ghi credential vào evidence.

Các check ngôn ngữ, nội dung và ngữ cảnh bắt buộc còn fail thì tiếp tục sửa nguyên
nhân, thêm regression và chạy lại; không thay kỳ vọng để làm xanh. Không train lại
router hoặc mở protected holdout. Không gọi một phép thử mock là Ollama thật.

Ghi HEAD, dirty/patch hash, command, exit code, kết quả passed/failed/skipped/unrun.
Không gán kết quả lịch sử cho source mới. Kiểm tra CI đúng SHA nếu truy cập được;
nếu không đọc được, ghi unverified. Không tự nhận production/Office Desktop đạt
khi chưa kiểm tra.

Nếu còn sửa mới, commit file cụ thể, chạy check bị ảnh hưởng rồi cập nhật main
bằng merge/push thông thường theo quyền người dùng đã cho. Không vượt branch
protection, không force-push. Xác minh full remote main SHA. Không deploy public.

Bàn giao link commit/main SHA, evidence đã làm sạch, kết quả live generation và
các yêu cầu còn thiếu. Chỉ xác nhận hoàn thành khi tất cả yêu cầu bắt buộc đạt.
```

## Kết quả local

- Bản export baseline trước sửa: 11 regression mới đều thất bại (exit 1).
- Source sau sửa: 11 regression đều đạt.
- Full pytest: 254 passed, không skip, 35.06s (exit 0).
- Node Web/auth/Office mock: 26 passed (exit 0).
- Ruff cho regression mới và git diff --check đạt.
- Không xác nhận live generation Windows hoặc CI từ các kết quả local này.
- Harness verify_memory_reliability.py: 10/10 nhóm đạt trên Gateway/FastAPI/SQLite/
  Chromium thật với provider offline có chủ ý. Evidence local được ignore:
  runtime/scope-empty-reply-final/report.json.
