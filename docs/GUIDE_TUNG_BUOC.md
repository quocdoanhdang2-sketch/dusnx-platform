# HƯỚNG DẪN LÀM DUSN-X TỪ ĐẦU ĐẾN CHẠY DEMO

> **Lưu ý phiên bản:** đây là hướng dẫn nền từ bản MVP. Với Phase 1 hiện tại, hãy bắt đầu bằng
> `README.md` và `docs/START_HERE_PHASE1.md`. Endpoint chuẩn có tiền tố `/api/v1`;
> các đoạn dùng `/api/events` bên dưới chỉ được giữ lại để đối chiếu lịch sử.

Tài liệu này dành cho Windows/PowerShell và bám theo kiến trúc DUSN-X v2.

---

## 0. Kết quả cuối cùng bạn sẽ có

Luồng chạy:

```text
Web / PowerPoint / Zalo
        -> ASP.NET Core Gateway
        -> Identity Mapping
        -> DUSN-X AI API (FastAPI)
        -> Global/Platform/Task State
        -> Adaptive Agent Router
        -> Conversation / Search-RAG / Productivity Agent
        -> Response + Feedback
        -> State phiên tiếp theo
```

Bản MVP này chạy được Web ngay. Zalo và PowerPoint đã có connector khởi đầu, nhưng để nối tài khoản thật bạn vẫn phải thêm credential/quyền chính thức của từng nền tảng.

---

# PHẦN A - CHUẨN BỊ MÁY

## Bước 1 - Tạo thư mục dự án

Khuyến nghị đặt ở ổ D:

```powershell
cd D:\Projects
mkdir DUSN-X-Platform-Phase1
```

Nếu bạn tải file ZIP của tôi, giải nén toàn bộ vào:

```text
D:\Projects\DUSN-X-Platform-Phase1
```

## Bước 2 - Kiểm tra công cụ

```powershell
python --version
git --version
docker --version
docker compose version
dotnet --version
```

Nên dùng Python 3.11 hoặc 3.12 cho project này. Nếu lệnh `python` trên máy bạn đang trỏ vào Python 3.14, hãy cài Python 3.12 song song và dùng `py -3.12`.

## Bước 3 - Tạo virtual environment

```powershell
cd D:\Projects\DUSN-X-Platform-Phase1
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Nếu PowerShell chặn script:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Sau đó mở PowerShell mới và kích hoạt lại.

## Bước 4 - Cài dependency Python

```powershell
python -m pip install --upgrade pip
pip install -e ".\python[dev]"
```

Thiết lập đường dẫn source:

```powershell
$env:PYTHONPATH="$PWD\python\src"
```

Kiểm tra:

```powershell
python -c "from dusnx_core.model import DUSNXModel; print('DUSN-X import OK')"
```

---

# PHẦN B - TẠO DATASET TEST

## Bước 5 - Sinh 10.000 event synthetic

Không train ngay 300K. Đầu tiên dùng 10K để kiểm tra pipeline.

```powershell
python .\python\scripts\generate_synthetic.py `
  --events 10000 `
  --users 500 `
  --out .\data\synthetic_10k.jsonl
```

Mỗi record có các trường chính:

```text
event_id
global_user_id
platform
session_id
event_time_utc
event_type
content
intent_label
selected_agent
next_action_label
feedback_value
task_success
synthetic
```

Ba platform của MVP:

```text
web
zalo
powerpoint
```

Dữ liệu này chỉ dùng để test code và huấn luyện prototype. Trong báo cáo phải ghi rõ `synthetic=true`.

## Bước 6 - Kiểm tra dataset

```powershell
Get-Content .\data\synthetic_10k.jsonl -TotalCount 3
```

Bạn phải thấy mỗi dòng là một JSON event.

---

# PHẦN C - KIỂM TRA MODEL

## Bước 7 - Chạy unit test

```powershell
pytest .\python\tests -q
```

Kỳ vọng:

```text
1 passed
```

## Bước 8 - Hiểu model đang train cái gì

Code lõi nằm ở:

```text
python/src/dusnx_core/model.py
```

DUSN-X v0.1 gồm:

```text
EventEncoder
   |-- hashed token embedding tự train
   |-- platform embedding
   |-- event type embedding
   |-- time gap
   `-- feedback

        -> event vector e_t

GlobalStateCell
PlatformStateCell
TaskStateCell
        -> S_t

S_t -> Intent Head
    -> Agent Router Head
    -> Next Action Head
```

Đây là phần tự train. Không dùng GPT/LLM để quyết định state hoặc router trong thí nghiệm lõi.

---

# PHẦN D - TRAIN LOCAL SMOKE MODEL

## Bước 9 - Mở config smoke

File:

```text
configs/smoke.yaml
```

Cấu hình này dùng model nhỏ, sequence ngắn và 10K event.

## Bước 10 - Train

```powershell
python .\python\scripts\train.py --config .\configs\smoke.yaml
```

Bạn sẽ thấy log dạng:

```text
users train/val/test=...
device=cpu hoặc cuda
parameters=...
epoch=1 train=... val=...
...
TEST {...}
checkpoint: artifacts/dusnx_smoke.pt
```

Kết quả tạo ra:

```text
artifacts/dusnx_smoke.pt
artifacts/dusnx_smoke.metrics.json
```

Không cần quan tâm score cao ngay lần đầu. Mục tiêu bước này là:

```text
model chạy
loss giảm
không NaN
checkpoint save/load được
```

---

# PHẦN E - CHẠY FASTAPI RIÊNG

## Bước 11 - Khởi động AI API

Mở PowerShell 1:

```powershell
cd D:\Projects\DUSN-X-Platform-Phase1
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH="$PWD\python\src"
$env:DUSNX_CHECKPOINT="$PWD\artifacts\dusnx_smoke.pt"
uvicorn apps.ai_api.main:app --app-dir .\python --reload --port 8000
```

Kiểm tra trình duyệt:

```text
http://localhost:8000/health
http://localhost:8000/docs
```

## Bước 12 - Test một event trực tiếp

PowerShell 2:

```powershell
$body = @{
  global_user_id = "demo-global-001"
  platform = "web"
  content = "nghiên cứu DUSN-X và tóm tắt phần trước"
  event_type = "message"
  time_gap_hours = 0
  feedback_value = 0.5
  previous_state = $null
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8000/v1/process `
  -ContentType "application/json" `
  -Body $body
```

Response phải có:

```text
intent
selected_agent
next_action
confidence
state_snapshot
agent_output
```

---

# PHẦN F - CHẠY ASP.NET CORE GATEWAY

## Bước 13 - Mở Gateway

PowerShell 3:

```powershell
cd D:\Projects\DUSN-X-Platform-Phase1\gateway-dotnet
$env:AI_API_URL="http://localhost:8000"
dotnet run --urls http://localhost:8080
```

Test:

```text
http://localhost:8080/health
```

## Bước 14 - Test identity mapping + state liên tục

```powershell
$event = @{
  platform = "web"
  platformUserId = "doanh-demo"
  content = "phân tích AI Agent"
  eventType = "message"
  feedbackValue = 0.7
  linkedUserId = "global-demo-001"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8080/api/v1/events `
  -ContentType "application/json" `
  -Body $event
```

Gửi tiếp request thứ hai với cùng `linkedUserId`. Bạn có thể đổi `platform` từ `web` sang `powerpoint` nhưng giữ `linkedUserId = "global-demo-001"` để chứng minh cùng một Global State đi xuyên nền tảng.

Bạn sẽ thấy:

```text
state_version: 1
state_version: 2
state_version: 3
...
```

Đó là cách chứng minh state được cập nhật qua chuỗi interaction.

---

# PHẦN G - CHẠY WEB DEMO

## Bước 15 - Chạy web bằng Docker hoặc server tĩnh

Cách dễ nhất sau khi AI API + Gateway đang chạy:

```powershell
cd D:\Projects\DUSN-X-Platform-Phase1\web-ui
python -m http.server 3000
```

Mở:

```text
http://localhost:3000
```

Nhập:

```text
Platform: web
User ID: demo-user-001
Nội dung: phân tích DUSN-X và làm tiếp phần hôm trước
```

Ấn **Gửi sự kiện**.

---

# PHẦN H - CHẠY TOÀN BỘ BẰNG DOCKER

## Bước 16 - Chạy compose

Trước tiên phải có checkpoint:

```text
artifacts/dusnx_smoke.pt
```

Sau đó:

```powershell
cd D:\Projects\DUSN-X-Platform-Phase1
docker compose up --build
```

Các cổng:

```text
Web      http://localhost:3000
Gateway  http://localhost:8080
AI API   http://localhost:8000
```

Dừng:

```powershell
docker compose down
```

Nếu muốn bật thêm Redis + SQL Server + MinIO:

```powershell
docker compose --profile infra up -d
```

Lưu ý: MVP hiện chạy state store trong RAM để bạn debug nhanh. SQL Server/Redis/MinIO là hạ tầng cho bước pilot sau.

---

# PHẦN I - NÂNG TỪ 10K LÊN 100K

## Bước 17 - Sinh 100K event

```powershell
python .\python\scripts\generate_synthetic.py `
  --events 100000 `
  --users 5000 `
  --out .\data\synthetic_100k.jsonl
```

Tạo một bản config mới:

```powershell
Copy-Item .\configs\smoke.yaml .\configs\train_100k.yaml
```

Sửa:

```yaml
data: data/synthetic_100k.jsonl
checkpoint: artifacts/dusnx_100k.pt
sequence_len: 12
batch_size: 32
epochs: 10
```

Train:

```powershell
python .\python\scripts\train.py --config .\configs\train_100k.yaml
```

Trên RTX 3050 4GB, nếu hết VRAM:

```text
giảm batch_size 32 -> 16 -> 8
giảm sequence_len 12 -> 8
```

Không nên ép 300K full experiment trên laptop.

---

# PHẦN J - TRAIN 300K TRÊN CLOUD

## Bước 18 - Sinh 300K dataset

```powershell
python .\python\scripts\generate_synthetic.py `
  --events 300000 `
  --users 10000 `
  --out .\data\synthetic_300k.jsonl
```

Config có sẵn:

```text
configs/prototype.yaml
```

## Bước 19 - Đẩy code lên GitHub

```powershell
git init -b main
git add .
git commit -m "Initial DUSN-X MVP"
```

Tạo repo trên GitHub rồi:

```powershell
git remote add origin <URL_REPO_CUA_BAN>
git push -u origin main
```

Không commit checkpoint lớn và dataset thật lên Git. `.gitignore` đã chặn `*.pt` và `data/*.jsonl`.

## Bước 20 - Cloud GPU

Trên Colab/Kaggle/RunPod, workflow là:

```text
1. Clone repository
2. Tạo Python 3.11/3.12 environment
3. pip install -e ./python
4. Đưa dataset vào data/
5. PYTHONPATH=python/src
6. python python/scripts/train.py --config configs/prototype.yaml
7. Tải artifacts/dusnx_prototype.pt về
8. Lưu metrics + config + seed + commit hash
```

Ví dụ Linux shell:

```bash
git clone <repo>
cd DUSN-X-Platform-Phase1
python -m pip install -e './python[dev]'
export PYTHONPATH=$PWD/python/src
python python/scripts/train.py --config configs/prototype.yaml
```

Cloud chỉ là nơi chạy training. Source code, config và checkpoint vẫn phải version hóa rõ ràng.

---

# PHẦN K - ZALO

## Bước 21 - Test adapter Zalo giả lập

Gateway có endpoint:

```text
POST /webhooks/zalo
```

Test:

```powershell
$zalo = @{
  eventId = "zalo-demo-001"
  userId = "zalo-user-001"
  message = "làm tiếp phần DUSN-X hôm qua"
  feedbackValue = 0.5
  linkedUserId = "global-demo-001"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8080/webhooks/zalo `
  -ContentType "application/json" `
  -Body $zalo
```

Khi nối Zalo thật, bạn thay adapter demo bằng webhook chính thức và phải kiểm tra token/signature/quyền theo tài liệu Zalo Developer hiện hành. Không hard-code secret vào source.

---

# PHẦN L - POWERPOINT

## Bước 22 - Hiểu connector PowerPoint

Thư mục:

```text
powerpoint-addin/
```

Có:

```text
manifest.xml
taskpane.html
taskpane.js
```

Taskpane gửi event:

```text
platform = powerpoint
```

về Gateway.

Để sideload Add-in thật, Office yêu cầu HTTPS cho taskpane. Vì vậy trước khi sideload, bạn cần chạy taskpane bằng HTTPS/dev certificate, rồi sửa `SourceLocation` trong `manifest.xml` cho đúng URL HTTPS của máy bạn.

MVP hiện tập trung chứng minh connector + event flow; phần thao tác shape/slide cụ thể sẽ thêm sau khi bạn chốt Office requirement set đang dùng.

---

# PHẦN M - THÍ NGHIỆM NGHIÊN CỨU

## Bước 23 - Baseline cần làm

Không chỉ train DUSN-X một model rồi kết luận.

Tối thiểu tạo các baseline:

```text
1. Most Frequent Agent
2. Static User Profile
3. Last Event Only
4. GRU State Model
5. Transformer Sequence Model
6. DUSN-X without time decay
7. DUSN-X without feedback
8. DUSN-X single platform
9. DUSN-X full
```

Bản code hiện cung cấp DUSN-X full pipeline. Baseline nên thêm sau khi MVP chạy ổn.

## Bước 24 - Metric

Ghi ít nhất:

```text
Intent Macro-F1
Router Macro-F1 / Accuracy
Next Action Macro-F1
P50/P95 latency
Cross-platform TransferGain
```

Công thức:

```text
TransferGain = Metric_cross_platform - Metric_single_platform
```

Thí nghiệm quan trọng:

```text
History: Web + Zalo
Target platform: PowerPoint

A = model chỉ dùng PowerPoint state
B = model dùng Global State + PowerPoint state

TransferGain = B - A
```

## Bước 25 - Chạy ít nhất 3 seed cho thí nghiệm chính

Ví dụ:

```text
42
123
2026
```

Mỗi run phải lưu:

```text
run_id
seed
git commit
dataset version
config
metric
checkpoint
GPU
training time
```

---

# PHẦN N - LỘ TRÌNH THỰC TẾ CHO MỘT NGƯỜI

Không làm tất cả một lúc.

```text
Mốc 1
10K synthetic + model chạy + FastAPI

Mốc 2
Web + Gateway + state_version

Mốc 3
100K data + metric + checkpoint

Mốc 4
PowerPoint connector

Mốc 5
Zalo connector

Mốc 6
300K cloud training

Mốc 7
Baseline + ablation + 3 seed

Mốc 8
SQL/Redis/MinIO + MLOps
```

Nếu một bước chưa ổn, không mở rộng sang bước sau.

---

# PHẦN O - CÁC FILE QUAN TRỌNG

```text
python/src/dusnx_core/model.py
    Lõi DUSN-X.

python/src/dusnx_core/dataset.py
    Window chuỗi theo user.

python/scripts/generate_synthetic.py
    Sinh dữ liệu prototype.

python/scripts/train.py
    Training + validation + test.

python/apps/ai_api/main.py
    FastAPI inference.

gateway-dotnet/Program.cs
    Gateway + identity mapping + state continuity.

web-ui/
    Demo Web.

powerpoint-addin/
    Connector PowerPoint MVP.

configs/
    Cấu hình training.
```

---

# PHẦN P - NHỮNG GÌ CHƯA NÊN GỌI LÀ PRODUCTION

Bản này là **research MVP runnable**, không phải production hoàn chỉnh. Trước production cần thay/thêm:

```text
In-memory state -> SQL Server + Redis State Service
Demo Zalo adapter -> webhook verified thật
PowerPoint taskpane HTTP -> HTTPS + Office dev cert
Demo Agent output -> RAG/tool/LLM thật
Synthetic dataset -> dataset có nguồn, consent, version, Dataset Card
Simple metrics -> full baseline/ablation/calibration
Local artifact -> S3/MinIO + model registry
```

Giữ ranh giới này trong báo cáo để không tuyên bố quá mức những gì prototype đã làm.
