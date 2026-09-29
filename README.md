# DUSN-X Platform — Phase 1 & Week 2 Implementation

**DUSN-X — Nền tảng trí tuệ cá nhân hóa thích ứng và hệ sinh thái AI đa tác nhân, đa nền tảng**

## Tuần 2 và benchmark pilot Tuần 3

Bằng chứng thực chạy ngày 28/09/2026: [nghiệm thu HTTP và Web Tuần 2](docs/WEEK2_ACCEPTANCE.md),
[kết quả và giới hạn pilot Tuần 3](docs/WEEK3_PILOT.md). Nhãn pilot **chưa được duyệt độc lập**.
Gateway dùng HttpClient proxy; auth dùng opaque token trong bảng SQLite `tokens`.

```powershell
# Từ thư mục gốc, sau khi activate virtualenv đã cài ./python[dev]
$env:PYTHONPATH="python/src;python;.;scripts"
python scripts/verify_real_ollama_week2.py --output runtime/week2-http.json
# UI thật: cần Playwright và Chromium (cài một lần)
python -m pip install playwright
python -m playwright install chromium
python scripts/verify_web_week2.py --output-dir runtime/week2-ui

python python/scripts/evaluate_personalization.py --validate-only
python python/scripts/evaluate_personalization.py --provider ollama --device cpu --output-dir runtime/week3-pilot
# Chỉ kiểm tra pipeline, không dùng số mock làm chất lượng LLM:
python python/scripts/evaluate_personalization.py --provider mock --device cpu --output-dir runtime/week3-mock

python -m pytest python/tests -q
node --test web-ui/app.test.js
dotnet build gateway-dotnet/Dusnx.Gateway.csproj -c Release
dotnet run --project gateway-dotnet.tests/Dusnx.Gateway.Tests.csproj -c Release
git diff --check
```

HTTP/UI cần dịch vụ chạy bằng `start-local.ps1`; benchmark dùng app FastAPI trong
process, DB riêng tại `runtime/week3-scratch/<run-id>`, Ollama thật ở `:11434`,
checkpoint local tại `artifacts/dusnx_smoke_v2.pt`. Không có checkpoint thì ghi
`bootstrap_rules`, không báo là kết quả model đã train. Script mặc định dùng CPU;
GPU là tùy chọn. Máy kiểm chứng dùng virtualenv có sẵn `python/.venv`, không cần
tạo lại nếu đã cài dependencies.

Pilot duy nhất về personalization là `benchmarks/week3_personalization_pilot.jsonl`
(12 chuỗi/36 bước), chuyển từ bản nháp phiên trước và bổ sung hai tình huống thiếu.
Các `benchmark_v1/v2_*` có sẵn là bộ chẩn đoán routing riêng, không bị thay thế.
Output: `predictions.jsonl`, `cases.json`, `summary.json`, `summary.md`, `errors.json`.
Dùng output-dir mới cho mỗi lượt để giữ bằng chứng trước. Nhãn không vào đầu vào
predict; không dùng dữ liệu benchmark để train. Đây là pilot AI biên soạn, không
phải holdout do người độc lập tạo; reviewer cần duyệt nhãn, diễn đạt tương đương,
phủ định và việc phân biệt nhớ đúng với đoán đúng. Chi tiết trong báo cáo Tuần 3.

## Các thành phần Tuần 2

- **Web Chatbot Cá nhân hóa chạy thật:** Đăng ký, đăng nhập với Opaque Bearer Token an toàn (lưu SQLite `tokens`), quản lý đa phiên (`/v1/sessions`), trò chuyện với trí nhớ thích ứng và kết nối trực tiếp với Ollama LLM thật cục bộ (`qwen2.5:0.5b`).
- **Điểm gọi API thống nhất qua Gateway ASP.NET Core:** Toàn bộ request Web UI (`:8080` ở chế độ Native hoặc `:3000` qua Nginx reverse-proxy ở Docker Compose) đều đi qua Gateway (`:8080`), giữ nguyên Authorization Bearer, error status code và body.
- **Một danh tính & state có thẩm quyền cho người dùng:** Các endpoint `/v1/me/events`, `/v1/me/state`, `/v1/me/events` trích xuất `user_id` trực tiếp từ token, tính toán `time_gap_hours`, chống giả mạo danh tính trong body.
- **Client thứ hai dùng chung state:** Client HTTP mô phỏng connector PowerPoint (phân biệt rõ với Office Add-in tích hợp thực tế) gửi event bằng token của tài khoản, đồng bộ và tăng `state_version` nhất quán với Web chat.
- **Trí nhớ có giải thích (Explainable RAG) & Cô lập Project:** Thuật toán chấm điểm theo độ tương quan và độ mới, cách ly nghiêm ngặt theo `project_id`, phản ánh chính xác `memory_ids_used` trong prompt.
- **Quản lý quyết định & Giải quyết mơ hồ:** Hỗ trợ lưu quyết định từ hội thoại ("Hãy nhớ rằng..."), sửa quyết định với bước xác nhận nguyên tử (đồng ý thì thay 1 lần, từ chối giữ bản cũ). Khi có 2 quyết định tương tự, hệ thống hỏi lại làm rõ thay vì sửa nhầm.
- **Xử lý lỗi Provider an toàn:** Khi LLM provider mất kết nối, lỗi được hiển thị dưới dạng thẻ lỗi chuyên dụng trên UI kèm nút Thử lại (Retry), tuyệt đối không lưu chuỗi lỗi vào lịch sử DB như câu trả lời AI hợp lệ.
- **Giao dịch nguyên tử & Idempotent Retry:** Cập nhật state và ghi user event trong một SQLite transaction thực sự; retry chat không nhân đôi tin nhắn/event/state version.

---

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
python .\python\scripts\generate_synthetic.py --events 30000 --users 1000 --out .\data\synthetic_30k_v2.jsonl --seed 42
$env:PYTHONPATH="python/src;python;."
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
- Training hỗ trợ FP16/mixed precision và gradient accumulation, cấu hình linh hoạt tự động nhận diện phần cứng GPU (CUDA) hoặc CPU fallback (`device: auto`).
- Docker Compose có profile `infra` và `rag` để tránh ngốn RAM khi chưa cần.

## Chạy nhanh trên Windows

Yêu cầu: Docker Desktop, Git, Python 3.12 và .NET 8.

### Đường 1: Chạy Native (Windows PowerShell)
```powershell
cd D:\Projects\dusnx-platform
.\start-local.ps1
```
Mở:
- Web UI & Gateway: `http://localhost:8080` (Gateway phục vụ cả static Web lẫn proxy `/v1/*` tới FastAPI)
- FastAPI: `http://localhost:8000/docs`

### Đường 2: Chạy Docker Compose
```powershell
cd D:\Projects\dusnx-platform
docker compose up --build
```
Mở:
- Web UI (Nginx reverse proxy): `http://localhost:3000` (Nginx proxy `/v1/*` và `/api/v1/*` tới Gateway)
- Gateway: `http://localhost:8080/health`
- FastAPI docs: `http://localhost:8000/docs`

Lần chạy đầu chưa cần checkpoint. API sẽ báo `runtime_mode=bootstrap_rules`.

## Ghi chú về checkpoint cũ

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup.ps1
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH="$PWD\python\src;$PWD\python;$PWD"
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

## Dữ liệu và train state/router trên local hoặc Colab

Notebook [train_dusnx_colab.ipynb](notebooks/train_dusnx_colab.ipynb), [hướng dẫn từng cú nhấp chuột](docs/TRAIN_COLAB_TUNG_BUOC.md) và [báo cáo sẵn sàng huấn luyện](docs/TRAIN_READINESS.md) phục vụ huấn luyện recurrent state và các đầu intent/agent/action, **không fine-tune LLM**. Toàn bộ mã nguồn, helper và CPU smoke đã được kiểm tra trên máy local; **chưa có phiên GPU nào được chạy trên Colab**. Không yêu cầu một loại GPU cụ thể; CPU chạy smoke 2-3 phút được.

```powershell
$env:PYTHONPATH='python/src;python;.;scripts'
python python/scripts/fetch_sources.py --source all
python python/scripts/import_data.py --source massive --input runtime/external-data/massive/vi-VN.jsonl --output-dir runtime/imported/massive
python python/scripts/prepare_data.py --legacy data/synthetic_30k_v2.jsonl
python python/scripts/pipeline_smoke.py --output runtime/new-smoke-run
python python/scripts/train.py --config configs/router_colab.yaml --checkpoint artifacts/new-router.pt
# Đánh giá 5 nhánh độc lập trên tập khóa holdout v2:
python python/scripts/evaluate_personalization.py --benchmark benchmarks/holdout_v2.jsonl --holdout-manifest benchmarks/holdout_v2.manifest.json --all-systems --include-model-only --provider mock --checkpoint artifacts/new-router.pt --output-dir runtime/eval_holdout_v2
```

Chọn output mới hoặc `--resume` cho train, không ghi đè checkpoint cũ. Pipeline dữ liệu xuất `runtime/prepared/{train,validation}.jsonl` và `manifest.json`; train xuất best `.pt`, `.last.pt`, config, metric/epoch; đánh giá xuất `predictions.jsonl`, `cases.json`, `summary.json/.md`, `errors.json`. Với bản clone thiếu 30k cũ, bỏ `--legacy`; khi đó dùng bank thiết kế 18 họ tình huống (843 event train / 141 event val). Xem [nguồn/license/revision](docs/DATA_SOURCES.md).

- **Holdout v1 (8 chuỗi/29 bước):** Đã bị xem xét và dùng để chẩn đoán hệ thống, nên không dùng để chọn model/rule.
- **Holdout v2 (10 chuỗi/38 bước, SHA-256 `1dfd8f1b...`):** Đã khóa độc lập làm benchmark mới chưa bị nhìn trước, bao quát unconfirmed claims, successive architecture, cache/theme rejections, ambiguity, cross-platform Web/PowerPoint.
- **MASSIVE vi-VN:** Đã tải nhưng toàn bộ mapping chờ reviewer duyệt nên bị loại hoàn toàn khỏi tập train; CSConDa chưa có quyền và được bỏ qua an toàn.
- **Đánh giá 5 nhánh:** Tách riêng `baseline_a` (no-memory), `baseline_b` (static-memory), `model_only` (pure checkpoint không qua rule), `dusnx_no_state` (ablation xóa recurrent state mỗi bước), và `dusnx` (full system). Kết quả cho thấy năng lực hiện tại của hệ thống đến chủ yếu từ SQLite CRUD và rules; giả thuyết recurrent state tốt hơn ablation chưa được chứng minh trên chuỗi ngắn (3-7 lượt).
- **Thẩm định nhãn độc lập:** File mẫu blind CSV tại `runtime/reviewer_package/holdout_v2_blind_template.csv` để gửi reviewer thứ hai độc lập gán nhãn mà không bị lộ dự đoán của model hay gold AI (xem [hướng dẫn duyệt](docs/ANNOTATION_GUIDE.md)).

## Đọc tiếp

- `docs/TRAIN_READINESS.md`: Báo cáo chi tiết về dữ liệu, leakage, 5 nhánh đánh giá và tình trạng sẵn sàng huấn luyện.
- `docs/TRAIN_COLAB_TUNG_BUOC.md`: Hướng dẫn 5 bước thao tác trên Google Colab lưu kết quả vào Google Drive.
- `docs/START_HERE_PHASE1.md`: thứ tự làm từng bước.
- `docs/INDEPENDENT_BENCHMARK_GUIDE.md`: schema và quy trình hai người để soạn benchmark độc lập.
- `docs/GITHUB_VA_MO_RONG.md`: cách đặt tên GitHub và thêm tính năng/connector.
- `docs/ARCHITECTURE.md`: kiến trúc tổng quan.
- `docs/GUIDE_TUNG_BUOC.md`: hướng dẫn MVP chi tiết cũ để tham khảo.

## Giới hạn Phase 1

- Chưa có JWT/refresh token. `/v1/me/state` yêu cầu opaque token; endpoint lịch sử
  `/api/v1/history/...` cũ vẫn là development-only.
- Zalo mới có normalized webhook skeleton, chưa ký request theo Zalo OA production.
- PowerPoint mới tạo outline/job; bước chèn slide bằng Office.js sẽ làm ở Phase 2.
- SQL Server, Redis, MinIO và ChromaDB đã có container profile nhưng chưa phải nguồn lưu trữ chính.
- `bootstrap_rules` chỉ để kiểm tra pipeline, không được báo cáo là kết quả model đã train.
