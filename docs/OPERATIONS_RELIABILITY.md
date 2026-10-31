# Vận hành và giới hạn đã kiểm tra trong cloud

Không phải chứng nhận production-ready. Không thay framework, ranh giới service
hoặc cấu trúc bảng SQLite. Không chạy deploy/commit/push, không xử lý dữ liệu thật.

## Cấu hình và truy cập

- Dev: Gateway làm entry; FastAPI/Ollama chỉ cục bộ hoặc mạng container nội bộ.
  Native không tự đọc .env; dùng biến process theo WINDOWS_NATIVE_RUNBOOK.
- Test: data directory và output mới, provider URL port trống cho phép thử offline
  mà không stop dịch vụ người dùng. Không đặt mock vào cấu hình sản phẩm.
- Production: domain/TLS, secret store, persistent volume, backup/retention, quyền
  vận hành và kiểm thử tải chưa có. Không bật Inspector/LLM evaluation hoặc remote
  development history. Không public FastAPI/Ollama.
- Gateway state/events legacy nay dùng cùng guard loopback/Origin với history.
  DUSNX_ALLOW_REMOTE_DEV_HISTORY là override **development** cho cả ba; tuyệt đối
  không coi nó là authentication production. Nhóm jobs/presentations/SignalR legacy
  vẫn cần chặn tại ingress hoặc thiết kế auth trước khi public toàn bộ Gateway.
- Zalo không cấu hình secret thì trả 503; Compose không cấp secret mẫu mặc định.
  Đây vẫn là normalized webhook, chưa có cơ chế chữ ký OA chính thức.
- Body JSON thực mới yêu cầu application/json; POST logout không body vẫn hoạt động.
  Body >1 MiB trả 413, content type sai trả 415 trong probe HTTP thực.
- Password mới dùng scrypt N=16384,r=8,p=1 và salt riêng, có version trong cột hash
  hiện có. Tài khoản SHA-256 cũ vẫn đăng nhập được và chỉ nâng cấp sau login đúng.
  Không reset password hay sửa account thật trong đợt này; test dùng DB tổng hợp.

## Backup, restore, retention và xóa

Theo [runbook Windows](WINDOWS_NATIVE_RUNBOOK.md#backuprestore): dùng SQLite backup
API; không copy riêng .db đang ghi WAL. Backup từng DB là snapshot từng DB. Nếu cần
auth/memory/Gateway state tại cùng một thời điểm, quiesce/stop đúng process đã xác
minh trước khi backup. Không tuyên bố backup từng DB là transaction xuyên service.

Harness đã backup auth.db/memory.db, PRAGMA integrity_check, copy vào **thư mục mới**
và start stack từ đó. Kiểm `/v1/auth/me` và memory bằng tài khoản tổng hợp trên bản
restore; không overwrite DB ban đầu. Khi restore dữ liệu thật phải xét token/revocation
bị quay về thời điểm snapshot và buộc đăng nhập lại theo policy vận hành.

Repo hiện xóa session và xóa mềm memory; lịch sử version, chat/event và receipt có
thể còn nội dung. Đây **không phải** quyền xóa vĩnh viễn toàn bộ dữ liệu tài khoản.
Chưa có retention tự động hoặc purge-account API đã xác minh. Không chạy DELETE/
VACUUM/purge trên dữ liệu người dùng trong tác vụ này. Cần người dùng xác định thời
gian lưu chat/events/receipts/backup, phạm vi xóa, quyền yêu cầu, audit và legal hold;
sau đó mới thiết kế purge có dry-run và kiểm restore/backup tương ứng. Không giả định
xóa bản active đã xóa mọi phiên bản hoặc mọi bản backup.

## Health và lỗi

Gateway /health kiểm identity/binary/AI URL; /v1/health proxy FastAPI và trả riêng
runtime_mode/checkpoint_loaded/provider_ok. 200/status=ok là liveness, không tự chứng
minh LLM hoặc database hoạt động. Health hiện chưa có database readiness probe trực
tiếp; dùng request auth/memory và SQLite check trong kiểm chứng local, không đổi schema
response chỉ để đánh dấu ready.

Đã thử trên process test thật:
- Provider port trống: provider_error; không lưu assistant error như câu trả lời,
  retry cùng request không nhân đôi user message.
- Mạng trình duyệt mất kết nối: Chromium hiện error card, không báo thành công.
- Memory write bị SQLite từ chối: HTTP lỗi, không có record mới; transaction rollback
  và ghi tiếp được. Lỗi trước patch giữ transaction/DB lock; runtime-02 ghi nhận lỗi,
  runtime-03 xác minh phục hồi. Lượt kiểm tra tiếp phát hiện lỗi SQLite chưa xử lý có
  thể đóng kết nối upstream; patch trả JSON 503 an toàn, không lộ query/DB path, rồi
  kiểm lại bằng runtime-final-02. Không tự retry mutation khi kết quả chưa xác định.
- Checkpoint hỏng: bootstrap_rules + checkpoint_loaded=false, warning đúng nguyên nhân;
  không giả model đã train.
- SQLite file hỏng: startup từ chối, log có DatabaseError; không tạo service ready giả.

Chưa kiểm generation thật, GPU, checkpoint production, provider timeout lâu, quota
dịch vụ ngoài hoặc tải nhiều user. Khóa RLock hiện giữ qua lời gọi LLM nên chat vẫn
tuần tự toàn process; đây là giới hạn throughput có bằng chứng từ review trước.
Tách network I/O khỏi khóa cần concurrency/idempotency design; không tự thay kiến trúc
hoặc bỏ khóa làm mất bảo vệ transaction trong patch này.

## Log và artifact

Không bật HTTP body/header logging. Không đưa password/Bearer token/URL query secret
vào evidence. Log probe chỉ dùng dữ liệu tổng hợp; runtime DB, backup, TLS private key
thử nghiệm và package review nằm dưới runtime/ được ignore, không đưa lên source.
Chưa thực hiện dependency CVE audit hoặc kiểm log toàn hệ thống production.

Artifact model phải pin code/data/base revision, lưu cấu hình, versions, hash và
evaluation report theo nhóm. Chỉ load checkpoint nguồn tin cậy đã đối chiếu checksum;
đường torch.load legacy có pickle nên checksum/nguồn tin cậy là điều kiện cần.
Chưa tạo candidate v2 hoặc đổi model production trong tác vụ này.

## Chạy lại đúng phạm vi

Tại root repo cloud, dùng python/.venv/bin/python và .NET 8 trên PATH:

```bash
python/.venv/bin/python scripts/verify_memory_reliability.py \
  --output-dir runtime/roadmap-check-NEW --chromium /usr/bin/chromium
node web-ui/app.test.js
node powerpoint-addin/taskpane.test.js
dotnet build gateway-dotnet/Dusnx.Gateway.csproj -c Release
dotnet run --project gateway-dotnet.tests/Dusnx.Gateway.Tests.csproj -c Release
git diff --check
```

Output phải mới; harness sở hữu và stop đúng child process, không kill theo cổng/tên.
Cần Playwright trong venv và Chromium có sẵn. Trên Windows dùng Python executable/
Chromium path thật; chưa tuyên bố harness mới đã chạy trên Windows. Không chạy cả
suite training/SFT/benchmark khi gate hiện tại đang đóng; chỉ chọn test ứng dụng.

Start/stop/update chuẩn Windows giữ theo runbook hiện có. Khi cập nhật: sao lưu/quiesce,
xem git status/diff, bảo vệ local changes, kiểm đúng checkpoint/provider và chạy kiểm
thử liên quan trước restart. Không reset/clean hoặc chép đè thư mục runtime người dùng.
