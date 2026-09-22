# DUSN-X Platform — Phase 1

Starter project cho **Cross-Platform Dynamic User State Network for Adaptive Multi-Agent Systems**.

## Phase 1 đã có gì?

- DUSN-X Core viết bằng PyTorch: Event Encoder, Time-Aware State Update, Global/Platform/Task State và Agent Router.
- FastAPI AI Service chạy được ở hai chế độ:
  - `bootstrap_rules`: demo ngay khi chưa có checkpoint.
  - `trained_dusnx`: tự chuyển sang model đã train khi có `artifacts/dusnx_smoke.pt`.
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
cd D:\Projects\DUSN-X-Platform-Phase1
docker compose up --build
```

Mở:

- Web demo: `http://localhost:3000`
- Gateway health: `http://localhost:8080/health`
- FastAPI health: `http://localhost:8000/health`
- FastAPI docs: `http://localhost:8000/docs`

Lần chạy đầu chưa cần checkpoint. API sẽ báo `runtime_mode=bootstrap_rules`.

## Huấn luyện checkpoint đầu tiên

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup.ps1
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH="$PWD\python\src"
python .\python\scripts\train.py --config .\configs\smoke.yaml
```

Sau khi sinh `artifacts/dusnx_smoke.pt`:

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
- `docs/GITHUB_VA_MO_RONG.md`: cách đặt tên GitHub và thêm tính năng/connector.
- `docs/ARCHITECTURE.md`: kiến trúc tổng quan.
- `docs/GUIDE_TUNG_BUOC.md`: hướng dẫn MVP chi tiết cũ để tham khảo.

## Giới hạn Phase 1

- Chưa có JWT/refresh token; endpoint xem state hiện là development-only.
- Zalo mới có normalized webhook skeleton, chưa ký request theo Zalo OA production.
- PowerPoint mới tạo outline/job; bước chèn slide bằng Office.js sẽ làm ở Phase 2.
- SQL Server, Redis, MinIO và ChromaDB đã có container profile nhưng chưa phải nguồn lưu trữ chính.
- `bootstrap_rules` chỉ để kiểm tra pipeline, không được báo cáo là kết quả model đã train.
