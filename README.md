# DUSN-X — Nền tảng trí tuệ cá nhân hóa thích ứng

DUSN-X là hệ thống chat đa nền tảng gồm Web UI, Gateway ASP.NET Core, AI API FastAPI,
bộ định tuyến neural đã train (DUSN-X Core), trí nhớ SQLite và truy xuất RAG có trích nguồn.
Router chọn ý định/agent/hành động; router **không sinh văn bản**. Câu trả lời do provider
bên ngoài (Gemini) hoặc Ollama cục bộ sinh ra.

**Không cần Docker Desktop để chạy bài.** Chế độ đang vận hành và đã nghiệm thu là
**native Windows** (AI API `:8000`, Gateway + Web `:8080`). Docker Compose chỉ là đường
tùy chọn cho ai muốn chạy container; máy hiện tại không bật Docker engine và điều đó
không ảnh hưởng gì.

Trạng thái chi tiết: [PROJECT_STATUS_20261107](docs/PROJECT_STATUS_20261107.md).
Vận hành native, stop/restart, backup: [WINDOWS_NATIVE_RUNBOOK](docs/WINDOWS_NATIVE_RUNBOOK.md).

## Trạng thái hiện tại

| Hạng mục | Hiện trạng |
| --- | --- |
| Web chat | Chạy native tại `http://127.0.0.1:8080`; Gateway phục vụ static Web và proxy `/v1/*` sang FastAPI |
| Router | `runtime_mode=trained_dusnx`, checkpoint Colab `router.pt` (`model_version=checkpoint:router.pt:sha256-56f56e6d61af:config-03b14389ce98`) |
| Provider | Production dùng Gemini `gemini-3.1-flash-lite` qua endpoint OpenAI-compatible; fallback Ollama/Qwen2.5 |
| Trí nhớ | SQLite `python/data/memory.db`: memory, chat session/message, project, receipt, event |
| RAG | SQLite FTS5 tại `python/data/rag.db`: 161 tài liệu / 1.415 chunk; câu trả lời trích `[S1]…` |
| Office | Word và PowerPoint Desktop đã nghiệm thu 09/11/2026 với Gemini; xem [bằng chứng Word](docs/evidence/word-addin-desktop-20261109/README.md), [bằng chứng PowerPoint](docs/evidence/powerpoint-addin-desktop-20261109/README.md) |
| SFT LLM | LoRA Qwen2.5-0.5B v3 đã train/đánh giá nhưng `promote=false`; model nền vẫn là model trả lời |
| Auth | Mật khẩu scrypt (nâng cấp từ SHA-256 cũ), opaque bearer token trong `python/data/auth.db`; **không phải JWT** |
| Docker | Tùy chọn, không bắt buộc; không phải nguồn lưu trữ chính |

## Kiến trúc ngắn

```text
Browser (web-ui)
   │  http://127.0.0.1:8080
   ▼
ASP.NET Core Gateway (:8080) ── static Web + proxy /v1/*, /api/v1/*
   │  Authorization được giữ nguyên
   ▼
FastAPI AI API (:8000)
   ├─ DUSN-X Core router  (intent / agent / next_action)
   ├─ State + SQLite memory + receipt
   ├─ RAG FTS5 (trích nguồn, không gọi provider cho câu hỏi dịch/viết lại)
   └─ Provider: Gemini (OpenAI-compatible) hoặc Ollama/Qwen2.5
```

- Dữ liệu người dùng: `python/data` (`auth.db`, `memory.db`, `rag.db`).
- Dữ liệu Gateway: `runtime/gateway-data`.
- Checkpoint, database, dataset và RAG index đều **không commit**.
- SQLite memory là kho dữ liệu quan sát được, **không phải hidden state** của model.

## Yêu cầu

Bắt buộc cho đường native:

- Windows 10/11 + PowerShell.
- Git.
- Python 3.11–3.13 (repo đang dùng `python/.venv`; máy mới có thể tạo `.venv` ở root).
- .NET 8 SDK.
- Một provider LLM:
  - **Ollama** + ít nhất một model Qwen2.5 (mặc định, chạy local), hoặc
  - **Gemini/OpenAI-compatible** + API key (production hiện dùng cách này).
- Checkpoint router local (`training-results/colab-run-01/.../router.pt` hoặc
  `artifacts/dusnx_smoke_v2.pt`). File `.pt` không có trong Git.

Tùy chọn:

- Node.js 18+ — chỉ cần cho test JS và dev server của Office add-in.
- Docker Desktop + WSL2 — chỉ khi chọn đường Docker.
- Chromium/Playwright — chỉ cho nghiệm thu Web UI tự động.

## Cài đặt lần đầu

```powershell
cd D:\Projects\dusnx-platform

# Nếu repo đã có python\.venv thì bỏ qua bước tạo venv
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".\python[dev]"

# Kiểm tra công cụ
python --version
dotnet --version
ollama list        # nếu dùng Ollama
```

Repo hiện có sẵn `python/.venv`; `start-local.ps1` tự dùng `.venv` ở root trước, rồi
`python/.venv`. Không cần cài lại nếu môi trường đã chạy được test.

### Provider: Ollama (mặc định, local)

```powershell
ollama pull qwen2.5:1.5b-instruct   # máy 4 GB VRAM
# hoặc qwen2.5:7b-instruct / qwen2.5:14b-instruct nếu máy đủ VRAM
ollama list
```

`start-local.ps1` mặc định `DUSNX_PROVIDER=ollama`, URL `http://127.0.0.1:11434`.
Model được chọn tự động theo VRAM; xem bảng bên dưới.

### Provider: Gemini / OpenAI-compatible (production)

Đặt biến môi trường trong PowerShell hiện tại hoặc biến user-level. Không ghi key vào
repo, file `.env` bị gitignore, log hay URL.

```powershell
$env:DUSNX_PROVIDER = "openai"
$env:DUSNX_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
$env:DUSNX_OPENAI_MODEL = "gemini-3.1-flash-lite"
$env:DUSNX_OPENAI_API_KEY = "<key-cua-ban>"
$env:DUSNX_OPENAI_TIMEOUT = "150"
$env:DUSNX_GATEWAY_TIMEOUT = "200"
```

Ghi chú:

- `start-local.ps1` **không tự đọc `.env`**; biến phải có trong môi trường chạy script.
- Provider ngoài lỗi/timeout sẽ fallback Ollama, trừ khi đặt `DUSNX_PROVIDER_FALLBACK=none`.
- Thiếu key sẽ báo lỗi cấu hình, không âm thầm coi là thành công.
- Có thể dùng OpenAI, LM Studio hoặc vLLM bằng cùng bộ biến `DUSNX_OPENAI_*`.

## Checkpoint router

`start-local.ps1` chọn checkpoint theo thứ tự:

1. `DUSNX_CHECKPOINT` nếu được đặt.
2. `training-results/colab-run-01/extracted/dusnx-router-full-01/router.pt`.
3. `artifacts/dusnx_smoke_v2.pt`.

Nếu không tìm thấy file, script **dừng trước khi launch** và báo thiếu checkpoint.
Đây là chủ ý: Web chat chỉ được coi là `trained_dusnx` khi router đã nạp thật.

Chỉ muốn xem pipeline ở chế độ `bootstrap_rules` (không có checkpoint), chạy riêng FastAPI:

```powershell
$env:PYTHONPATH = "$PWD\python;$PWD\python\src"
cd python
.\.venv\Scripts\python.exe -m uvicorn apps.ai_api.main:app --host 127.0.0.1 --port 8000
```

Khi đó `/health` báo `runtime_mode=bootstrap_rules`; không được báo đây là kết quả model
đã train. Muốn có Web UI đầy đủ vẫn cần Gateway và checkpoint.

## Chạy bài (native — khuyến nghị)

```powershell
cd D:\Projects\dusnx-platform
.\start-local.ps1
Start-Process http://127.0.0.1:8080
```

Mở:

- Web UI + Gateway: `http://127.0.0.1:8080`
- FastAPI docs: `http://127.0.0.1:8000/docs`

Kiểm tra:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health | ConvertTo-Json -Depth 6
Invoke-RestMethod http://127.0.0.1:8080/health | ConvertTo-Json -Depth 6

# Phải thấy: service=dusnx-ai-api, runtime_mode=trained_dusnx,
# checkpoint_loaded=true, model_version khác rỗng, provider_ok=true.
(Invoke-RestMethod http://127.0.0.1:8000/health).model_profile | ConvertTo-Json
```

`start-local.ps1` kiểm tra:

- Hai cổng `8000/8080` có đúng service DUSN-X không; không kill process lạ.
- Hash source FastAPI và binary Gateway có khớp working tree không; process cũ bị từ chối.
- Proxy `/v1/health` và trang Web trả đúng nội dung trước khi báo thành công.
- Log khởi động ở `runtime/startup` (không commit).

Stop/restart:

```powershell
.\scripts\stop-local.ps1
.\start-local.ps1
```

Chạy stack thử ở cổng khác, không đụng production:

```powershell
.\start-local.ps1 -AiPort 8100 -GatewayPort 8180
.\scripts\stop-local.ps1 -AiPort 8100 -GatewayPort 8180
```

## Chạy bằng Docker (tùy chọn)

Chỉ dùng khi đã bật Docker Desktop/WSL2. Không cần cho đường native.

```powershell
cd D:\Projects\dusnx-platform
docker compose up --build
```

Mở:

- Web qua Nginx: `http://localhost:3000`
- Gateway: `http://localhost:8080/health`
- FastAPI docs: `http://localhost:8000/docs`

Lưu ý Docker:

- Compose mount `./artifacts` vào `/app/artifacts` (read-only). Checkpoint mặc định là
  `/app/artifacts/dusnx_smoke_v2.pt`; thiếu file thì AI API báo `bootstrap_rules`.
  Không đặt đường dẫn Windows trong `.env` dùng cho container.
- Provider mặc định là Ollama qua `http://host.docker.internal:11434`.
- Trong container không thấy VRAM host; đặt `DUSNX_MODEL_VRAM_GB=4` (hoặc 8/16) để
  resolver chọn đúng tier, hoặc ép `DUSNX_OLLAMA_MODEL`.
- `docker compose down` để dừng.
- Profile mở rộng `infra` (Redis, SQL Server, MinIO) và `rag` (ChromaDB) chỉ để thử,
  chưa phải nguồn lưu trữ chính:
  `docker compose --profile infra up --build`.

## Sử dụng Web UI

1. Đăng ký tài khoản mới rồi đăng nhập (không dùng tài khoản thật của người khác).
2. Chat: mỗi phiên có trí nhớ riêng theo user; câu trả lời có thể hiển thị nguồn RAG,
   thẻ "Trí nhớ đã dùng (n)" và nút sao chép.
3. Ghi nhớ bằng câu lệnh rõ ràng:
   - `nhớ rằng tôi thích trà sen vàng`
   - `nhớ là ngày mai họp lúc 9 giờ`
   - `ghi nhớ quyết định dùng SQLite cho bản local`
   Nếu chỉ gõ tiền tố mà không có nội dung (`nhớ rằng`, `nhớ là`), hệ thống hỏi lại
   thay vì lưu chuỗi rỗng nghĩa.
4. Màn **Trí nhớ**: xem, tìm, thêm tay, hiện cả bản đã bị thay thế.
5. Màn **Dự án**: quyết định đang hiệu lực và lịch sử quyết định.
6. **Timeline** là công cụ dev/local, chỉ loopback; không bật
   `DUSNX_ALLOW_REMOTE_DEV_HISTORY=true` ngoài môi trường kiểm soát.

Office add-in:

- Word: [WORD_ADDIN_RUNBOOK](docs/WORD_ADDIN_RUNBOOK.md) — task pane HTTPS `:3001`,
  proposal được duyệt trước khi Apply, kiểm tra lại selection trước khi ghi.
- PowerPoint: [POWERPOINT_ADDIN_RUNBOOK](docs/POWERPOINT_ADDIN_RUNBOOK.md) — tạo outline,
  duyệt rồi chèn slide; chưa có tạo ảnh.

## RAG và trích nguồn

Index RAG nằm ở `python/data/rag.db` (không commit). Corpus là tài liệu và mã nguồn
trong repo, **không** lấy từ dataset huấn luyện hay dữ liệu người dùng.

```powershell
# Rebuild index local (chỉ khi cần; thao tác này ghi đè rag.db local)
$env:PYTHONPATH = "$PWD\python;$PWD\python\src"
.\python\.venv\Scripts\python.exe -c "from apps.ai_api import rag; print(rag.build_index(force=True))"
```

- Câu trả lời có bằng chứng mạnh sẽ trích `[S1]`, `[S2]`… và chỉ hiển thị nguồn đã dùng.
- Câu hỏi dịch/viết lại và yêu cầu Office bỏ qua retrieval để tránh trích tài liệu sai ngữ cảnh.
- Kiểm tra runtime: `python scripts/verify_rag_web.py http://127.0.0.1:8080`.

## Model thích nghi theo máy

AI API tự chọn Qwen2.5 vừa VRAM, chỉ trong các model **đã cài** (không tự tải):

| VRAM | Tier | Thứ tự ưu tiên |
| --- | --- | --- |
| dưới 6 GB | `low` | `qwen2.5:1.5b-instruct` → 3B → 0.5B |
| 6–12 GB | `mid` | `qwen2.5:7b-instruct` → 3B → 1.5B |
| từ 12 GB | `high` | `qwen2.5:14b-instruct` → 7B → 3B |

- Ép model: `DUSNX_OLLAMA_MODEL=qwen2.5:3b-instruct` (thắng auto).
- Ép tier: `DUSNX_MODEL_PROFILE=low|mid|high`.
- Không thấy GPU (CPU-only, Docker, Apple Silicon): đặt `DUSNX_MODEL_VRAM_GB=4|8|16`.
- Auto không chọn `qwen3:*` (phát `<think>`) và không chọn candidate `dusnx-vi-*`
  (chưa promote); chỉ dùng khi đặt tên tường minh.
- Kiểm tra: `(Invoke-RestMethod http://127.0.0.1:8000/health).model_profile`.

## Kiểm thử

Dừng stack trước khi build/test Gateway, vì process đang chạy giữ khóa
`gateway-dotnet/bin/Release/net8.0/Dusnx.Gateway.dll`.

```powershell
cd D:\Projects\dusnx-platform

# Python
.\python\.venv\Scripts\python.exe -m pytest python\tests -q

# JavaScript (Node built-in test runner, không cần npm install)
node --test web-ui/app.test.js web-ui/auth.test.js word-addin/dev-server.test.js word-addin/word-taskpane.test.js powerpoint-addin/taskpane.test.js

# Gateway
dotnet build gateway-dotnet\Dusnx.Gateway.csproj -c Release
dotnet run --project gateway-dotnet.tests\Dusnx.Gateway.Tests.csproj -c Release
```

Nếu vẫn muốn build khi production Gateway đang chạy, xuất ra thư mục khác:

```powershell
dotnet build gateway-dotnet.tests\Dusnx.Gateway.Tests.csproj -c Release -p:OutDir="$PWD\runtime\tmp\gwtest\"
dotnet "$PWD\runtime\tmp\gwtest\Dusnx.Gateway.Tests.dll"
```

Kỳ vọng: toàn bộ pass, 0 fail. Unit test chỉ là kiểm tra hồi quy; nghiệm thu runtime
phải dùng `/health` và chat thật qua Gateway, không dùng mock làm bằng chứng.

## Bảo mật và giới hạn đã biết

- Không commit `.env`, API key, token, database, dataset, checkpoint hay RAG index.
  Key chỉ đặt trong biến môi trường hoặc file local đã gitignore.
- Auth dùng scrypt + opaque bearer token (tối đa 10 token/user), chưa có JWT/refresh token.
- `/api/v1/history/...` và Timeline là endpoint dev/local, mặc định chỉ loopback.
- Router không sinh văn bản. Chất lượng câu trả lời phụ thuộc provider và RAG.
- SFT v3 (0.5B LoRA) chưa được promote; không báo cáo là model production.
- RAG chỉ trả lời từ corpus repo; không bảo đảm thông tin thời sự bên ngoài.
- Office add-in chưa có tạo ảnh và chưa có guard cho tracked changes.
- Redis, SQL Server, MinIO, ChromaDB chỉ là profile thử nghiệm, chưa phải storage chính.
- Không chạy lại benchmark/holdout đã xem prediction để tune hoặc promote model.

## Tài liệu

- [Kiến trúc](docs/ARCHITECTURE.md)
- [Vận hành native Windows](docs/WINDOWS_NATIVE_RUNBOOK.md)
- [Hợp đồng phản hồi chat](docs/CHAT_RESPONSE_CONTRACT.md)
- [Trạng thái dự án](docs/PROJECT_STATUS_20261107.md)
- [Roadmap sau Tuần 4](docs/POST_WEEK4_ROADMAP.md)
- [Báo cáo Tuần 4](docs/WEEK4_COMPLETION_REPORT.md)
- [Checkpoint Colab Run 01](docs/CHECKPOINT_COLAB_RUN_01.md)
- [Hướng dẫn train router trên Colab](docs/TRAIN_COLAB_TUNG_BUOC.md)
- [Runbook Word add-in](docs/WORD_ADDIN_RUNBOOK.md)
- [Runbook PowerPoint add-in](docs/POWERPOINT_ADDIN_RUNBOOK.md)
- [Độ tin cậy vận hành](docs/OPERATIONS_RELIABILITY.md)
- [Hiệu năng và bảo mật](docs/PERFORMANCE_AND_SECURITY_REPORT.md)
- [Hành vi VI/EN/auto](docs/BILINGUAL_BEHAVIOR.md)

Lịch sử nghiệm thu Tuần 2/3/4 và các quyết định cũ nằm trong `docs/`; README này mô tả
trạng thái và cách chạy hiện hành. Khi tài liệu lịch sử mâu thuẫn với README, ưu tiên
`/health`, mã nguồn và bằng chứng runtime mới nhất.
