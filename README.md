# DUSN-X Platform — Phase 1

## Checkpoint v2 (default runtime)

The default checkpoint is `artifacts/dusnx_smoke_v2.pt`. It is local-only: do not commit checkpoints, datasets, `.env`, or secrets.

Windows native and Docker use different paths for the same mounted artifact:

- Native: `D:\Projects\dusnx-platform\artifacts\dusnx_smoke_v2.pt` (or another host path through `DUSNX_CHECKPOINT`).
- Docker Compose: `/app/artifacts/dusnx_smoke_v2.pt` (or another **container** path through `.env`). Do not put a Windows path in `.env` for Docker.

### Create the v2 dataset and checkpoint on Windows

```powershell
cd D:\Projects\dusnx-platform
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
Push-Location .\python
python -m pip install -e ".[dev]"
Pop-Location
python .\python\scripts\generate_synthetic.py --events 30000 --users 1000 --out .\data\synthetic_30k_v2.jsonl
python .\python\scripts\train.py --config .\configs\smoke_v2.yaml
```

### Run and verify native Windows

```powershell
cd D:\Projects\dusnx-platform
.\start-local.ps1
Invoke-RestMethod http://127.0.0.1:8000/health | ConvertTo-Json -Depth 10
```

`/health` must show `runtime_mode` as `trained_dusnx`, a non-empty `checkpoint_loaded` pointing to the host v2 checkpoint, and a non-empty `model_version`. The same `model_version` is written to each `state_snapshot`.

### Timeline local và smoke test xuyên nền tảng

Endpoint timeline là công cụ quan sát **dev/local**, chưa có authentication production.
Mặc định Gateway chỉ trả endpoint này cho request loopback. Không bật
`DUSNX_ALLOW_REMOTE_DEV_HISTORY=true` ngoài môi trường development được kiểm soát.

```powershell
cd D:\Projects\dusnx-platform
.\start-local.ps1

# Gửi một event và đọc trang timeline mới nhất (tối đa 100 record/trang).
$body = @{
  platform = "web"
  platformUserId = "web-demo"
  linkedUserId = "local-demo-shared"
  content = "Tìm tài liệu về DUSN-X"
  eventType = "message"
  feedbackValue = 0.0
} | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8080/api/v1/events -Method Post -ContentType application/json -Body $body
Invoke-RestMethod "http://127.0.0.1:8080/api/v1/history/web/web-demo?linkedUserId=local-demo-shared&limit=25"

# Smoke test tự tạo linked key duy nhất rồi gửi Web → Zalo → PowerPoint.
.\smoke-test.ps1
```

Kết quả timeline được sắp mới nhất trước. Nếu response có `next_cursor`, truyền nó qua
query `before` để lấy trang cũ hơn. Cùng `linkedUserId` cho ba platform sẽ dùng chung
identity; khác linked key sẽ tách lịch sử. `known_feedback_value` luôn là feedback đã
biết trước event hiện tại.

Các lựa chọn Zalo/PowerPoint trong Web UI chỉ mô phỏng request đầu vào. Router chỉ đề
xuất `next_action`; phiên bản này chưa gửi tin Zalo, chưa chỉnh file PowerPoint, chưa
thực hiện Internet search/RAG retrieval thật. `routing_source=business_rule_override`
cho biết route cuối đã được rule thay đổi, nhưng API hiện không trả thêm dự đoán model
thuần cho từng event.

Smoke test ghi record với prefix/run ID duy nhất vào `runtime/gateway-data`. Có thể xóa
toàn bộ thư mục đó khi chắc chắn không cần giữ bất kỳ state local nào; script không tự
xóa hoặc đụng dữ liệu có sẵn.

### Run and verify Docker Compose

```powershell
cd D:\Projects\dusnx-platform
docker compose up --build
Invoke-RestMethod http://127.0.0.1:8000/health | ConvertTo-Json -Depth 10
```

For Docker, `.env` uses `/app/artifacts/dusnx_smoke_v2.pt`; `checkpoint_loaded` must report that container path. If the checkpoint is absent, FastAPI correctly reports `bootstrap_rules` and returns an exact v2 generation/training command in `metadata.warning`.

Starter project cho **Cross-Platform Dynamic User State Network for Adaptive Multi-Agent Systems**.

## Phase 1 đã có gì?

- DUSN-X Core viết bằng PyTorch: Event Encoder, Time-Aware State Update, Global/Platform/Task State và Agent Router.
- FastAPI AI Service chạy được ở hai chế độ:
  - `bootstrap_rules`: demo ngay khi chưa có checkpoint.
  - `trained_dusnx`: tự chuyển sang model đã train khi có `artifacts/dusnx_smoke_v2.pt`.
- ASP.NET Core API Gateway với `/api/v1`, Problem Details và event validation.
- State được lưu xuống `runtime/gateway-data`, không mất ngay khi Gateway restart.
- Presentation job bất đồng bộ: `queued → processing → completed/failed`.
- SignalR Hub skeleton tại `/hubs/jobs`.
- Zalo webhook queue skeleton tại `/webhooks/zalo`.
- Web demo cho event và Presentation Job.
- PowerPoint Add-in skeleton gọi Presentation Job API.
- Script tạo dữ liệu synthetic có nhãn rõ ràng.
- Training hỗ trợ FP16 và gradient accumulation cho RTX 3050 Laptop 4 GB.
- Docker Compose có profile `infra` và `rag` để tránh ngốn RAM khi chưa cần.

## Chạy nhanh trên Windows

Yêu cầu: Docker Desktop, Git, Python 3.12 và .NET 8.

```powershell
cd D:\Projects\dusnx-platform
docker compose up --build
```

Mở:

- Web demo: `http://localhost:3000`
- Gateway health: `http://localhost:8080/health`
- FastAPI health: `http://localhost:8000/health`
- FastAPI docs: `http://localhost:8000/docs`

Lần chạy đầu chưa cần checkpoint. API sẽ báo `runtime_mode=bootstrap_rules`.

## Ghi chú về checkpoint cũ

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup.ps1
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH="$PWD\python\src"
python .\python\scripts\train.py --config .\configs\smoke_v2.yaml
```

Sau khi sinh `artifacts/dusnx_smoke_v2.pt`:

```powershell
docker compose down
docker compose up --build
```

Kiểm tra `http://localhost:8000/health`. `runtime_mode` phải chuyển thành `trained_dusnx`.

## Chạy hạ tầng mở rộng

Chỉ bật khi cần:

```powershell
# Redis + SQL Server + MinIO
docker compose --profile infra up --build

# Thêm ChromaDB
docker compose --profile infra --profile rag up --build
```

## Tạo GitHub repository

Mày có thể tự đặt tên repository. Tên đề xuất:

- `dusnx-platform`
- `DUSN-X`
- `cross-platform-dusnx`

Sau khi tạo repository rỗng trên GitHub:

```powershell
git init -b main
git add .
git commit -m "feat: initialize DUSN-X phase 1"
git remote add origin git@github.com:quocdoanhdang2-sketch/TEN_REPOSITORY.git
git push -u origin main
```

Thay `TEN_REPOSITORY` bằng tên mày chọn. Không commit `.env`, dataset thật, checkpoint hoặc secret.

## Đọc tiếp

- `docs/START_HERE_PHASE1.md`: thứ tự làm từng bước.
- `docs/INDEPENDENT_BENCHMARK_GUIDE.md`: schema và quy trình hai người để soạn benchmark độc lập.
- `docs/GITHUB_VA_MO_RONG.md`: cách đặt tên GitHub và thêm tính năng/connector.
- `docs/ARCHITECTURE.md`: kiến trúc tổng quan.
- `docs/GUIDE_TUNG_BUOC.md`: hướng dẫn MVP chi tiết cũ để tham khảo.

## Giới hạn Phase 1

- Chưa có JWT/refresh token; endpoint xem state hiện là development-only.
- Zalo mới có normalized webhook skeleton, chưa ký request theo Zalo OA production.
- PowerPoint mới tạo outline/job; bước chèn slide bằng Office.js sẽ làm ở Phase 2.
- SQL Server, Redis, MinIO và ChromaDB đã có container profile nhưng chưa phải nguồn lưu trữ chính.
- `bootstrap_rules` chỉ để kiểm tra pipeline, không được báo cáo là kết quả model đã train.
