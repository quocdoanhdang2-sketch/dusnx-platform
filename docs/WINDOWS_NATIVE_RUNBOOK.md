# DUSN-X — vận hành native Windows

## Chuẩn bị và setup

Git, Python 3.11–3.13, .NET 8, Node (chạy tests), Ollama đã cài base
`qwen2.5:0.5b`. CPU được hỗ trợ. Router Colab giữ local, không tải lại/train lại
trong nghiệm thu Tuần 4. Chromium/Playwright chỉ cần cho nghiệm thu Web.

```powershell
Set-Location D:\Projects\dusnx-platform
# Dùng venv sẵn có. Nếu máy mới:
py -3.12 -m venv .venv
& .venv/Scripts/python.exe -m pip install -e './python[dev]'
ollama list
# Chỉ khi chưa có base trên máy mới:
# ollama pull qwen2.5:0.5b
```

`.env.example` là danh mục cấu hình, script native **không tự đọc .env**.
Đặt biến trong PowerShell trước khi chạy. Docker dùng đường container và volume
của docker-compose, không dùng đường host Windows trong container.

## Start và health

```powershell
$env:DUSNX_CHECKPOINT = 'training-results/colab-run-01/extracted/dusnx-router-full-01/router.pt'
$env:DUSNX_DEVICE = 'cpu'
$env:DUSNX_PROVIDER = 'ollama'
$env:DUSNX_OLLAMA_URL = 'http://localhost:11434'
$env:DUSNX_OLLAMA_MODEL = 'qwen2.5:0.5b'
$env:DUSNX_ENABLE_LLM_EVAL = '0'
./start-local.ps1
Invoke-RestMethod http://127.0.0.1:8000/health | ConvertTo-Json -Depth 5
Invoke-RestMethod http://127.0.0.1:8080/health | ConvertTo-Json -Depth 5
Invoke-RestMethod http://127.0.0.1:8080/v1/health | ConvertTo-Json -Depth 5
Start-Process http://127.0.0.1:8080
```

Checkpoint và đường data tương đối được resolve theo project root, không theo cwd.
Native mặc định tiếp tục dùng `python/data` cho SQLite như startup cũ; Gateway dùng
`runtime/gateway-data`. Không di chuyển/ghi đè DB có sẵn. Nếu trước đây đặt
`DUSNX_DATA_DIR` tương đối theo cwd khác, truyền **đường tuyệt đối tới DB cũ**.
Nghiệm thu dùng `-AiDataDir runtime/week4-native-ai -GatewayDataDir runtime/week4-native-gateway`.

Health yêu cầu `service=dusnx-ai-api`, `api_contract=week4-v1`,
`runtime_mode=trained_dusnx`, `checkpoint_loaded=true`, đúng đường/model version.
`provider_ok` health chỉ true nếu provider reachable và model cấu hình tồn tại.
Gateway health có `service=dusnx-gateway`, `binary_sha256`, đúng `ai_api_url`.
Startup đối chiếu hash source FastAPI và binary Gateway để phát hiện process cũ.
Health không chứng minh đã sinh câu trả lời: chat phải có `provider_called=true`,
`response_source=llm`, model thực trả về. Recall template không gọi Ollama.

## Stop/restart và port conflict

```powershell
# Chỉ stop PID có health đúng, command line thuộc repo và PID chưa bị tái sử dụng:
./scripts/stop-local.ps1
./start-local.ps1
# Port bận: xem owner, không kill theo tên python/dotnet hoặc stop ứng dụng khác.
Get-NetTCPConnection -State Listen | Where-Object LocalPort -in 8000,8080 |
  Select-Object LocalPort,OwningProcess
# Stack khác cổng, vẫn phục vụ Web cùng origin:
./start-local.ps1 -AiPort 8100 -GatewayPort 8180
# Stop cùng cổng đã chọn:
./scripts/stop-local.ps1 -AiPort 8100 -GatewayPort 8180
```

Startup từ chối port của ứng dụng không xác minh được; không stop WordPress/Docker.
Nếu health không đáp ứng, xem PID/command line trong Task Manager hoặc CIM trước khi
thao tác. Không dùng `Stop-Process -Name python`. Chỉ process do mình xác minh mới
được dừng. Log startup local ở `runtime/startup`, không đưa log nguyên bản lên Git.

## Checkpoint/provider/model và retry

- Checkpoint thiếu: startup dừng trước launch; FastAPI chạy riêng báo bootstrap,
  `checkpoint_loaded=false`. Checkpoint sai: health bootstrap và warning; giữ nguyên
  checkpoint gốc, kiểm SHA rồi chọn artifact đúng.
- Ollama chưa chạy: mở Ollama hoặc `ollama serve` trong terminal riêng; kiểm `/api/tags`
  và `ollama list`. Không cần dừng Ollama để thử offline: dùng URL port trống ở stack test riêng.
- Model thiếu: `provider_ok=false`, chat `provider_error` với `model_missing`. Không tự
  chuyển sang candidate. Cài đúng base trên máy mới hoặc sửa config rồi restart process đã xác minh.
- Lỗi HTTP/timeout/JSON/schema có mã riêng; không được lưu thành assistant reply thành công.
  Gateway timeout mặc định 90 giây, Ollama 60 giây; `DUSNX_GATEWAY_TIMEOUT` nên lớn hơn
  timeout provider cộng thời gian xử lý. Gateway không tự retry mutation.
- Web dùng `request_id` giữ nguyên khi retry. Receipt thành công replay nguyên response,
  không tăng memory/state/messages; provenance gốc được giữ riêng, replay không gọi provider.
  Nếu process ngắt giữa mutation và receipt thì server
  trả 409 “kết quả chưa xác định”: kiểm lịch sử/memory trước khi gửi yêu cầu mới.
  Client cũ không gửi request ID chỉ có bảo vệ retry legacy theo nhánh, không được xem là
  đảm bảo exactly-once toàn hệ thống. Native runbook dùng một FastAPI worker.
- State malformed bị từ chối 409; state khác model/schema được reset theo policy đã có,
  kèm `state_reset/reset_reason`. GET state phản ánh metadata đang lưu và tính tương thích.

Evaluation mặc định tắt. Chỉ bật ở stack riêng với `DUSNX_ENABLE_LLM_EVAL=1` và
`DUSNX_LLM_EVAL_MODELS=qwen2.5:0.5b,dusnx-vi-candidate`; yêu cầu Bearer token,
allowlist và không lưu prompt vào DB. Không đặt token ở URL hoặc command line.
Không chạy lại test đã xem prediction để tune/promote model.

## Backup/restore

SQLite WAL: không copy chỉ file `.db` khi service đang ghi. Dùng SQLite backup API
vào thư mục local mới, hoặc stop đúng service trước khi copy toàn bộ data directory.
Ví dụ backup nhất quán từng DB bằng Python chuẩn (không cần credentials):

```powershell
$env:DUSNX_BACKUP_SOURCE = (Resolve-Path python/data).Path
$env:DUSNX_BACKUP_TARGET = Join-Path $PWD ('runtime/backups/' + (Get-Date -Format yyyyMMdd-HHmmss))
@'
import os, sqlite3
from pathlib import Path
source = Path(os.environ['DUSNX_BACKUP_SOURCE'])
target = Path(os.environ['DUSNX_BACKUP_TARGET'])
target.mkdir(parents=True, exist_ok=False)
for name in ('auth.db', 'memory.db'):
    with sqlite3.connect(f'file:{(source/name).as_posix()}?mode=ro', uri=True) as src:
        with sqlite3.connect(target/name) as dst:
            src.backup(dst)
            assert dst.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
print('Local SQLite backups verified')
'@ | & python/.venv/Scripts/python.exe -
```

Để có snapshot đồng thời auth/memory/Gateway JSON, stop stack trước backup cả thư mục.
Restore: stop verified stack; giữ bản backup DB hiện tại; copy snapshot vào **thư mục mới**,
truyền `-AiDataDir`/`-GatewayDataDir` tới snapshot đó rồi kiểm health/login/memory.
Không overwrite/xóa DB gốc hoặc commit backups. Runbook không tự chạy restore.

## Kiểm chứng lại

```powershell
$env:PYTHONPATH='python/src;python;.;scripts'
$py='python/.venv/Scripts/python.exe' # hoặc .venv/Scripts/python.exe
& $py -m pytest python/tests -q --tb=short
node --test web-ui/app.test.js
dotnet build gateway-dotnet/Dusnx.Gateway.csproj -c Release
dotnet run --project gateway-dotnet.tests/Dusnx.Gateway.Tests.csproj -c Release
./scripts/tests/local-health.tests.ps1
# Dùng DB test riêng; output phải mới. Không dùng DB người thật.
& $py scripts/verify_week4_runtime.py --data-dir runtime/week4-native-ai --output-dir runtime/week4-new-run
& $py scripts/verify_week4_web.py --output-dir runtime/week4-new-browser
git diff --check
```

Browser: cài `playwright` và `python -m playwright install chromium` một lần trong venv.
Hai script tạo tài khoản giả, không đọc DB cá nhân; script runtime khởi tạo các process
lỗi riêng, terminate đúng child handle và giữ stack chính. Báo cáo nằm ở output riêng,
không lưu token/password. Không dùng TestClient/mock để thay bằng chứng native/browser.
