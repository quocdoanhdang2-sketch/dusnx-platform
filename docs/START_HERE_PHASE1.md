# Bắt đầu DUSN-X — Phase 1

## Mục tiêu của Phase 1

Hoàn thành một lát cắt end-to-end:

```text
Web/PowerPoint/Zalo event
        ↓
ASP.NET Core Gateway
        ↓
FastAPI + DUSN-X
        ↓
Global User State được cập nhật
        ↓
Agent Router trả về Agent phù hợp
```

## Việc 1 — Chạy bootstrap demo

```powershell
docker compose up --build
```

Mở `http://localhost:3000`, giữ `Linked user key` giống nhau và gửi lần lượt:

1. Platform `web`: `phân tích AI Agent`.
2. Platform `zalo`: `tóm tắt tiếp phần đang nghiên cứu`.
3. Platform `powerpoint`: `tạo 5 slide từ phần đó`.

Kết quả mong đợi: `state_version` tăng sau mỗi lần gửi.

## Việc 2 — Kiểm thử Presentation Job

Ở phần `Presentation Job bất đồng bộ`, chọn số slide rồi nhấn tạo. Trạng thái phải chạy:

```text
queued → processing → completed
```

## Việc 3 — Tạo dữ liệu 10K và train smoke model

```powershell
.\setup.ps1
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH="$PWD\python\src"
python .\python\scripts\train.py --config .\configs\smoke.yaml
```

Không gọi dữ liệu này là dữ liệu thật. File do script tạo có trường `synthetic=true`.

## Việc 4 — Kiểm tra model đã được dùng

Restart Docker rồi mở `http://localhost:8000/health`.

```json
{
  "runtime_mode": "trained_dusnx"
}
```

Nếu vẫn là `bootstrap_rules`, kiểm tra file:

```text
artifacts/dusnx_smoke.pt
```

## Definition of Done

- Web gửi được ba loại platform event.
- Cùng linked key tạo cùng global user.
- State version tăng liên tục.
- Presentation Job hoàn thành.
- Có checkpoint smoke.
- Python tests và .NET build đều chạy qua.
- Code được commit lên repository GitHub do mày tạo.
