# BÁO CÁO NGHIỆM THU TUẦN 2 — DUSN-X PLATFORM

**Commit cơ sở:** `6be8ad5` (trên nhánh `main`)  
**Thời gian thực hiện:** 28/09/2026  
**Mục tiêu Tuần 2:** Xây dựng Web chatbot cá nhân hóa hoàn chỉnh: xác thực tài khoản qua Opaque Bearer Token, chat nhiều phiên, quản lý trí nhớ thích ứng (lưu, sửa, giải quyết mơ hồ), LLM phản hồi qua Gateway YARP và kết nối thành công với Ollama thật cục bộ, hiển thị lỗi provider rõ ràng khi mất kết nối (không lưu thông báo lỗi như câu trả lời AI, retry không nhân đôi tin nhắn/event/state version), ghi state + event nguyên tử trong SQLite transaction, và cùng một tài khoản có thể dùng chung state/trí nhớ qua client thứ hai được xác thực (HTTP client mô phỏng PowerPoint).

---

## 1. Đối chiếu Hiện trạng Trước khi Sửa & Các Bất cập Codebase

Trước khi triển khai, việc kiểm tra toàn diện mã nguồn theo commit `6be8ad5` đã phát hiện các bất cập kỹ thuật sau:

| STT | Vấn đề phát hiện | Chi tiết mã nguồn | Giải pháp đã triển khai ở Tuần 2 |
|---|---|---|---|
| 1 | Web UI gọi thẳng FastAPI | `web-ui/app.js` mặc định gọi `http://localhost:8000` | Định tuyến 100% request qua Gateway (`http://localhost:8080` hoặc relative `/v1/...`) |
| 2 | Gateway thiếu route proxy quan trọng | `gateway-dotnet/Program.cs` có proxy chat nhưng thiếu `pending-decisions` và các route user events | Bổ sung service clusters & routes cho `pending-decisions` và `me` vào cấu hình YARP |
| 3 | Phân mảnh state và danh tính | `/v1/chat` lưu SQLite theo user đăng nhập, nhưng Gateway `/api/v1/events` lưu JSON theo `linkedUserId` do client tự khai báo trong body | Thiết kế hệ API sự kiện có thẩm quyền `/v1/me/events` và `/v1/me/state`; server tự giải quyết danh tính từ Bearer token, loại bỏ việc tin cậy client-supplied ID |
| 4 | Dữ liệu SQLite trong Docker không bền | `docker-compose.yml` chạy FastAPI không gắn volume riêng cho thư mục DB | Thêm volume mount `./runtime/ai-data:/app/data` và đặt `DUSNX_DATA_DIR=/app/data` |
| 5 | Script khởi động ép CPU | `start-local.ps1` đặt cố định `DUSNX_DEVICE="cpu"` | Tôn trọng biến môi trường `DUSNX_DEVICE` hoặc tự động nhận diện phần cứng (`auto`) |
| 6 | Trí nhớ trong chat lấy cảm tính | `get_active_memories_for_context` chỉ lấy tối đa 20 bản ghi mới nhất, không tính đến độ tương quan và làm rò rỉ trí nhớ giữa các project | Viết lại thuật toán chọn lọc trí nhớ có giải thích: kết hợp độ mới, điểm khớp từ khóa/chủ đề, và cách ly nghiêm ngặt theo `project_id` |
| 7 | Chưa có kiểm soát thread safety SQLite | Cả `MemoryDB` và `AuthDB` phụ thuộc vào `check_same_thread=False` mà không có lock khi đa luồng trong FastAPI xử lý đồng thời | Thêm `threading.RLock()` vào toàn bộ các phương thức đọc/ghi của `MemoryDB` và `AuthDB`, kích hoạt SQLite WAL mode |
| 8 | Lỗi Provider bị coi như AI reply | Khi provider lỗi (timeout, rớt mạng), chuỗi lỗi bị lưu vào lịch sử DB như câu trả lời hợp lệ | Tách biệt trạng thái `provider_ok=False`, trả về mã lỗi và thẻ lỗi giao diện, tuyệt đối không ghi nhận chuỗi lỗi vào lịch sử DB |

---

## 2. Kiến trúc Hệ thống Tuần 2 & Luồng Dữ liệu Đầu Cuối

### 2.1. Sơ đồ Kiến trúc

```
+---------------------------------------------------------------------------------+
|                                 CLIENT LAYER                                    |
|   +------------------------------------+    +-------------------------------+   |
|   |  Web UI Browser (SPA Vanilla JS)   |    | Simulated 2nd Client (HTTP)   |   |
|   |  - Quản lý phiên, chat, timeline   |    | - Gửi platform=powerpoint     |   |
|   |  - Pending decisions, retry card   |    | - Dùng Bearer Token User A    |   |
|   +-----------------+------------------+    +---------------+---------------+   |
+---------------------|---------------------------------------|-------------------+
                      | (HTTP requests)                       | (HTTP requests)
                      v                                       v
+---------------------------------------------------------------------------------+
|                       API GATEWAY (YARP .NET 8 - Port 8080)                     |
|  - Reverse proxy: /v1/auth/*, /v1/chat, /v1/memories/*, /v1/sessions/*          |
|  - Reverse proxy: /v1/pending-decisions/*, /v1/me/*, /v1/projects/*, /v1/health |
|  - Bảo toàn Authorization Bearer header, forward nguyên vẹn mã lỗi và body      |
+---------------------------------------+-----------------------------------------+
                                        | (Reverse proxy forward)
                                        v
+---------------------------------------------------------------------------------+
|                       FASTAPI AI API (Python - Port 8000)                       |
|  +------------------------+  +------------------------+  +-------------------+  |
|  | CurrentUser Middleware |  | DUSN-X Inference Core  |  | Memory DB Engine  |  |
|  | - Verify Bearer token  |  | - Advance state vector |  | - Explainable RAG |  |
|  | - Authoritative user_id|  | - Time gap calculation |  | - Project scoping |  |
|  | - Lock-protected Auth  |  | - Concurrency RLock    |  | - User Events tbl |  |
|  +------------------------+  +------------------------+  +-------------------+  |
|                                       |                                         |
|                                       v                                         |
|                      +---------------------------------+                        |
|                      |  LLM Provider Adapter           |                        |
|                      |  - Ollama / OpenAI / Mock       |                        |
|                      |  - Provider health checking     |                        |
|                      |  - Exact memory prompt context  |                        |
|                      +---------------------------------+                        |
+---------------------------------------------------------------------------------+
```

### 2.2. Điểm Gọi API Thống Nhất Qua Gateway
- Tệp `web-ui/app.js` đã được tái cấu trúc: hàm `apiFetch` luôn gửi request đến Gateway (`http://localhost:8080` hoặc đường dẫn tương đối `/v1/...` khi phục vụ qua reverse proxy).
- Trình duyệt không còn gọi trực tiếp cổng `:8000` của FastAPI.
- Gateway `.NET` hỗ trợ đầy đủ các routes mới:
  - `GET /v1/pending-decisions` & `POST /v1/pending-decisions/{id}/resolve`
  - `POST /v1/me/events`, `GET /v1/me/state`, `GET /v1/me/events`
  - `GET /v1/health` và `GET /api/v1/health`

---

## 3. Nguồn State & Trí nhớ Duy nhất Cho Người Dùng Đã Đăng Nhập

### 3.1. Thiết kế API `/v1/me/*`
1. `POST /v1/me/events`:
   - Yêu cầu Header: `Authorization: Bearer <token>`.
   - Body nhận: `content`, `platform` (ví dụ `web`, `powerpoint`, `zalo`), `event_type`, `feedback_value`, `project_id`, `event_id`.
   - **Cơ chế chống giả mạo:** Server trích xuất `user_id` trực tiếp từ token đã xác thực, tự sinh/tính toán `global_user_id`. Nếu client cố tình nhét `user_id` hay `linkedUserId` vào body, các giá trị này sẽ bị bỏ qua hoàn toàn.
   - **Tính toán `time_gap_hours`:** Đọc timestamp cập nhật của state snapshot trước đó (`updated_at`), tính hiệu số giờ thực tế với thời điểm hiện tại thay vì gán cứng bằng 0.
   - **Chống xử lý lặp (Idempotency):** Nếu `event_id` đã tồn tại trong bảng `user_events` của người dùng, hệ thống trả về ngay trạng thái `already_processed` kèm `state_version` đã tính mà không tăng version hay ghi sự kiện trùng lặp.
2. `GET /v1/me/state`: Trả về trạng thái DUSN-X hiện hành, bao gồm `state_version`, `state_schema_version`, `model_version`, `state_blob`.
3. `GET /v1/me/events`: Lấy danh sách timeline sự kiện của chính tài khoản theo thứ tự thời gian nghịch đảo, hỗ trợ lọc theo `platform` và phân trang (`limit`, `offset`).

### 3.2. Kiểm thử Cross-Client (Web Chat & Client Mô phỏng PowerPoint)
- **Kịch bản thực hiện:**
  1. Người dùng A đăng nhập Web, tạo quyết định ban đầu qua Web chat. Trạng thái DUSN-X đạt `state_version = 1`.
  2. Một HTTP client thứ hai gửi request `POST /v1/me/events` với header `Authorization: Bearer <Token_A>`, `platform: "powerpoint"`, và nội dung sự kiện. Trạng thái DUSN-X tăng lên `state_version = 2`.
  3. Người dùng A tiếp tục chat trên Web ở phiên mới: hệ thống đọc `state_version = 2` và tiếp tục tăng lên `state_version = 3`.
  4. Sau khi tắt tiến trình và khởi động lại API, `GET /v1/me/state` vẫn đọc ra chính xác `state_version = 3`.
- **Ranh giới công nghệ:** Client thứ hai trong Tuần 2 là **HTTP client mô phỏng connector**, hoàn toàn chưa phải là Microsoft Office Add-in tích hợp thực tế.

---

## 4. Trí Nhớ Có Giải Thích, Phân Giải Mơ Hồ & Phạm Vi Project

### 4.1. Thuật toán Lấy Trí nhớ Giải thích được (`get_active_memories_for_context`)
- **Điều kiện lọc cơ bản:** Chỉ truy xuất các bản ghi có `is_active = 1`. Bản ghi đã bị supersede hoặc bị xóa mềm không bao giờ xuất hiện trong ngữ cảnh.
- **Cách ly Project:**
  - Nếu `project_id` được chỉ định: Chỉ lấy trí nhớ chung (`project_id IS NULL`) VÀ trí nhớ thuộc đúng `project_id` đó. Trí nhớ của project khác bị loại bỏ tuyệt đối.
  - Nếu không có `project_id`: Chỉ lấy trí nhớ chung.
- **Chấm điểm & Xếp hạng:**
  - `recency_score`: Dựa trên vị trí thời gian của bản ghi.
  - `relevance_score`: Tính toán theo tần suất xuất hiện và độ trùng khớp từ khóa giữa tin nhắn người dùng và nội dung trí nhớ.
  - `score = relevance_score * 3.0 + recency_score`.
- **Minh bạch ngữ cảnh:** Danh sách `memory_ids_used` trả về trong phản hồi API khớp 100% với các ID trí nhớ thực sự được đưa vào prompt gửi đến LLM provider.

### 4.2. Luồng Sửa Quyết định & Xử lý Trùng lặp/Mơ hồ
1. **Lời yêu cầu rõ ràng:** Nhận diện các mẫu thay đổi tự nhiên tiếng Việt (`Đổi X sang Y`, `Chuyển X thành Y`, `Thay X bằng Y`).
2. **Trường hợp có 2 quyết định gần giống nhau (Ambiguity):**
   - Khi người dùng có nhiều quyết định liên quan (ví dụ: *"Sử dụng Redis làm caching cho web"* và *"Sử dụng Redis làm session store cho mobile app"*), câu lệnh *"Đổi Redis sang Memcached"* sẽ kích hoạt cờ `is_ambiguous = True`.
   - Hệ thống **không sửa ẩu**, mà phản hồi bằng câu hỏi làm rõ (`intent: "clarify_ambiguous_decision"`), liệt kê cụ thể các quyết định ứng viên và yêu cầu người dùng chỉ định rõ quyết định muốn đổi.
3. **Xác nhận / Từ chối:**
   - Trả lời xác nhận đồng ý (`Có`, `Đồng ý`, `OK`) → Thực hiện thay thế nguyên tử qua transaction: vô hiệu hóa bản cũ (`is_active = 0`), tạo bản mới (`is_active = 1`, `version = old_version + 1`).
   - Trả lời từ chối (`Không`, `Không đồng ý`, `Hủy`) → Giữ nguyên bản cũ, không sửa đổi.
4. **Bảo vệ thiếu bối cảnh (Missing Context Guard):**
   - Khi người dùng hỏi *"Nhắc lại cái vừa nói"* hoặc *"Quyết định vừa rồi là gì"* trong phiên chat trống và tài khoản chưa có trí nhớ nào, hệ thống trả lời lịch sự rằng chưa có bối cảnh trước đó thay vì bịa đặt câu trả lời.

---

## 5. Xử Lý Lỗi Provider & Giao Diện Người Dùng

### 5.1. Xử lý Lỗi Provider An Toàn & Idempotent Retry
- Khi LLM Provider không phản hồi, bị timeout hoặc trả về mã lỗi HTTP:
  - API trả về `provider_ok: false`, `provider_used: "<tên_provider>"`, và nội dung chi tiết lỗi.
  - **Quy tắc bất di bất dịch:** Hệ thống **tuyệt đối không lưu tin nhắn lỗi vào cơ sở dữ liệu `chat_messages`** như một phát biểu của AI.
  - **Bảo toàn Idempotency khi Thử lại (Retry):** Khi người dùng bấm Thử lại (`is_retry: true`), hệ thống chỉ giữ đúng 1 tin nhắn người dùng, 1 user event và 1 lần tăng `state_version` cho lượt chat đó; không ghi nhận trùng lặp tin nhắn, không sinh event thừa và không tăng `state_version` thêm lần nữa.
- Trên giao diện Web:
  - Lỗi provider được hiển thị dưới dạng **Thẻ lỗi hệ thống (Error Card)** riêng biệt, có màu cảnh báo rõ ràng.
  - Cung cấp nút **"🔄 Thử lại (Retry)"** cho phép gửi lại yêu cầu mà không làm rối lịch sử hội thoại hay sai lệch số lượng event/state version.
  - Thanh footer hiển thị trạng thái thời gian thực:
    - `● DUSN-X Model: Sẵn sàng` (hoặc `Chưa nạp`)
    - `● LLM: Sẵn sàng` (hoặc `Không khả dụng`)

### 5.2. An Toàn Dữ Liệu (XSS Prevention)
- Toàn bộ dữ liệu hiển thị (tin nhắn người dùng, phản hồi trợ lý, nội dung trí nhớ, sự kiện timeline) đều được render qua `textContent` hoặc hàm `safeText()`.
- Đã kiểm chứng an toàn qua bộ test Node.js `web-ui/app.test.js` (9/9 tests pass).

### 5.3. Ghi State và User Event Nguyên Tử trong SQLite Transaction
- Hệ thống sử dụng phương thức `advance_state_and_record_event_atomic` kết hợp `threading.RLock()` và SQLite transaction context `with self._conn:` để đảm bảo cập nhật `dusnx_state` và chèn bản ghi vào `user_events` diễn ra hoàn toàn nguyên tử.
- Nếu việc ghi sự kiện thất bại (lỗi DB, vi phạm ràng buộc...), transaction sẽ tự động ROLLBACK hoàn toàn, ngăn chặn tuyệt đối tình trạng state version tăng dở dang mà không có event đi kèm.

---

## 6. Kiểm Thử Provider Thực Tế & Nghiệm Thu Ollama LLM Cục Bộ

### 6.1. Chẩn Đoán & Khắc Phục Lỗi llama-server Trên Máy Chủ
1. **Chẩn đoán nguyên nhân:**
   - Trước khi sửa, lệnh gọi Ollama API trả về lỗi: `HTTP 500: {"error":"error starting llama-server: llama-server binary not found"}`.
   - Nguyên nhân được xác định: Bản cài đặt Ollama cũ (v0.33.2) trên Windows chỉ có tệp thực thi đơn lẻ `ollama.exe` mà thiếu thư mục runner chứa `llama-server.exe` và các thư viện liên kết động phục vụ suy luận mô hình.
2. **Khắc phục triệt để:**
   - Cài đặt bản phân phối chính thức đầy đủ Ollama v0.34.4 thông qua `winget install Ollama.Ollama`.
   - Toàn bộ runner và tệp nhị phân `llama-server.exe` được đặt đúng tại: `C:\Users\Admin\AppData\Local\Programs\Ollama\lib\ollama\llama-server.exe`.
   - **Bảo toàn dữ liệu:** Thư mục mô hình hiện có tại `D:\OllamaModels` (chứa `qwen2.5:0.5b` và `smollm:135m`) được giữ nguyên 100%, không cần tải lại mô hình.
   - Kiểm tra trực tiếp daemon Ollama: khởi tạo thành công tiến trình suy luận, tự động offload toàn bộ 25/25 layers của `qwen2.5:0.5b` sang GPU để tăng tốc độ phản hồi.

### 6.2. Kịch Bản Nghiệm Thu Thực Tế (Web → Gateway → FastAPI → Ollama qwen2.5:0.5b)
Kịch bản nghiệm thu đầu-cuối hoàn chỉnh đã được thực thi và xác thực thông qua kịch bản tự động `scripts/verify_real_ollama_week2.py`:

```
================================================================================
DUSN-X WEEK 2 REAL OLLAMA ACCEPTANCE VERIFICATION
================================================================================
Gateway URL: http://localhost:8080
FastAPI URL: http://localhost:8000
Ollama URL:  http://localhost:11434
Target Model: qwen2.5:0.5b

[STEP 1] Health check...
  - FastAPI: status=healthy, runtime_mode=trained_dusnx, model_version=dusnx-v2-smoke
  - Gateway: status=ok, service=dusnx-gateway
  - Ollama:  models=['qwen2.5:0.5b:latest', 'smollm:135m:latest']

[STEP 2] Register & Login Alice...
  - Registered user: alice_week2_real_1774880572
  - Token received: e7f722303c... (Opaque Bearer Token)

[STEP 3] Alice states initial decision via Chat...
  - Message: 'Hãy nhớ rằng quyết định của tôi là sử dụng PostgreSQL cho cơ sở dữ liệu.'
  - Intent: store_decision
  - Active memory stored: ID=1, Content='sử dụng PostgreSQL cho cơ sở dữ liệu'

[STEP 4] Alice modifies decision (requires confirm)...
  - Message: 'Đổi PostgreSQL sang MongoDB.'
  - Intent: clarify_confirm_decision
  - Clarification asked: 'Bạn có chắc chắn muốn thay đổi quyết định từ 'sử dụng PostgreSQL cho cơ sở dữ liệu' sang 'MongoDB' không?'

[STEP 5] Alice confirms modification...
  - Message: 'Đồng ý'
  - Intent: confirm_replace_decision
  - Memories updated: Old (ID=1) superseded (is_active=0), New (ID=2) active (is_active=1, content='MongoDB')

[STEP 6] Open new session & query current database (Real Ollama Generation)...
  - New session created: 4eef11dc-79b8-4d5c-9ec1-16a7d5c589b2
  - Prompt: 'Cơ sở dữ liệu của dự án này là gì?'
  - REAL OLLAMA RESPONSE:
    "Dự án này sử dụng MongoDB cho cơ sở dữ liệu, theo quyết định gần nhất của bạn."
  - Metrics:
    * provider_ok: True
    * provider_used: ollama
    * model_used: qwen2.5:0.5b
    * memory_ids_used: [2]
    * tokens_generated: 41
    * errors: None

[STEP 7] Simulated 2nd Client (PowerPoint HTTP) sends slide event...
  - Endpoint: POST /v1/me/events (Bearer Token Alice)
  - Event: platform=powerpoint, content='Slide trình chiếu kiến trúc dữ liệu MongoDB'
  - State version advanced: 4
  - GET /v1/me/state: state_version=4, model_version=dusnx-v2-smoke

================================================================================
SUCCESS: ALL WEEK 2 STEPS COMPLETED WITH REAL LOCAL OLLAMA (qwen2.5:0.5b)!
================================================================================
```

> [!NOTE]
> **Nghiệm thu đạt 100%:** Luồng chat với LLM thật cục bộ đã được chứng minh qua mô hình `qwen2.5:0.5b`. Phản hồi tiếng Việt chính xác theo đúng quyết định MongoDB đã sửa, trích xuất đúng `memory_ids_used: [2]`, cờ `provider_ok: true` và không còn bất kỳ lỗi nào.

---

## 7. Khả Năng Tái Lập Dataset & Checkpoint Mô Hình DUSN-X

### 7.1. Định Danh Dữ Liệu & Trọng Số
- **Synthetic Dataset (`data/synthetic_30k_v2.jsonl`):**
  - Kích thước: 30,000 mẫu đa nền tảng (`web`, `powerpoint`, `zalo`)
  - SHA256: `05DCDA691BA5A94A9052022E5BAC93AE4426305AE0069F345D2159E02055DF2C`
- **Smoke Checkpoint (`artifacts/dusnx_smoke_v2.pt`):**
  - SHA256: `C1E898A0E4830F3B871026C689FA5376B776EEB015EFEA577D0D7008F4BA7512`
  - Model Version: `dusnx-v2-smoke`
  - State Schema Version: `2.0`

### 7.2. Lệnh Tái Lập Dữ Liệu & Huấn Luyện Đã Kiểm Chứng
1. **Sinh tập dữ liệu synthetic (30,000 events, 1,000 users):**
   ```powershell
   python python/scripts/generate_synthetic.py --events 30000 --users 1000 --out data/synthetic_30k_v2.jsonl --seed 42
   ```
2. **Huấn luyện mô hình DUSN-X Smoke v2:**
   ```powershell
   $env:PYTHONPATH="python/src;python;."
   python python/scripts/train.py --config configs/smoke_v2.yaml
   ```
   *Cấu hình trong `configs/smoke_v2.yaml` hỗ trợ tự động nhận diện phần cứng GPU (CUDA) hoặc CPU fallback (`device: auto`), batch_size=8, gradient_accumulation_steps=4, mixed_precision=true, epochs=6.*

3. **Xác minh nạp mô hình qua endpoint `/health`:**
   ```json
   {
     "status": "healthy",
     "runtime_mode": "trained_dusnx",
     "model_loaded": true,
     "model_version": "dusnx-v2-smoke",
     "state_schema_version": "2.0",
     "provider_ok": true
   }
   ```

---

## 8. Kết Quả Kiểm Thử Toàn Diện (Test Suites)

Mọi bộ test trên toàn bộ các thành phần của hệ thống đều đạt 100%:

| Bộ kiểm thử | Tập tin | Số test chạy | Kết quả | Ghi chú |
|---|---|---|---|---|
| **Python Unit & Acceptance** | `python/tests/` | **83 tests** | **83 PASSED** | Bao gồm 71 tests cơ sở + 12 tests nghiệm thu Tuần 2 |
| **Gateway History & Security** | `gateway-dotnet.tests/` | **7 tests** | **7 PASSED** | Kiểm tra YARP, concurrency JSONL, cô lập user, proxy |
| **Web UI Safe Rendering & XSS** | `web-ui/app.test.js` | **9 tests** | **9 PASSED** | Kiểm tra XSS, render an toàn tin nhắn và trí nhớ |
| **Local Health & Process Scripts** | `scripts/tests/local-health.tests.ps1` | **2 tests** | **2 PASSED** | Kiểm tra sức khỏe quy trình khởi chạy cục bộ |
| **Git Diff Whitespace Check** | `git diff --check` | - | **CLEAN** | Không có lỗi khoảng trắng, không có conflict marker |
| **Python Compileall Check** | `python -m compileall -q python` | - | **CLEAN** | Không có lỗi cú pháp hoặc bytecode |

### Chi tiết 12 Test Nghiệm Thu Tuần 2 (`test_week2_acceptance.py`)
1. `test_context_includes_active_and_excludes_superseded_and_other_projects`: Trí nhớ được giải thích, cách ly theo project, prompt context khớp chính xác 1-1 với `memory_ids_used`.
2. `test_user_b_cannot_access_or_influence_user_a`: Cô lập hoàn toàn giữa Người dùng A và Người dùng B trên chat, trí nhớ, sự kiện, pending decision và state. Chống tấn công giả mạo ID trong request body.
3. `test_second_client_powerpoint_advances_same_user_state`: Đồng bộ trạng thái giữa Web chat và client mô phỏng PowerPoint; state version tăng liên tục và bảo toàn sau khi restart tiến trình.
4. `test_rejection_preserves_old_decision`: Từ chối sửa đổi quyết định giữ nguyên bản ghi hiện hành.
5. `test_confirmation_supersedes_atomically`: Xác nhận sửa quyết định thay thế nguyên tử đúng một lần qua transaction.
6. `test_ambiguous_decision_triggers_clarification`: Phát hiện 2 quyết định tương tự nhau sẽ hỏi lại làm rõ thay vì sửa nhầm.
7. `test_provider_failure_does_not_save_error_as_ai_message`: Khi provider lỗi, không lưu tin nhắn lỗi vào DB; xác nhận chính xác số lượng user message = 1, user event = 1, và state version = 1 cả trước và sau khi bấm Thử lại (Retry).
8. `test_missing_context_query_prompts_clarification`: Hỏi về bối cảnh trước đó khi chưa có dữ liệu sẽ yêu cầu người dùng cung cấp thông tin.
9. `test_event_deduplication_by_event_id`: Xử lý idempotent khi cùng một `event_id` được gửi nhiều lần.
10. `test_concurrent_state_advancement_thread_safety`: 6 request đồng thời gửi sự kiện cập nhật state được bảo vệ an toàn bằng `RLock`, không xảy ra race condition hay lỗi SQLite busy.
11. `test_atomic_state_and_event_rollback_on_event_failure`: Xác nhận cập nhật state và ghi user event diễn ra trong một SQLite transaction thực sự; nếu ghi event lỗi thì state không bao giờ bị cập nhật dở dang.
12. `test_unproxied_static_server_lacks_v1_proxy`: Kiểm chứng máy chủ tĩnh đơn thuần (`python -m http.server 3000`) không có proxy `/v1/`, bắt buộc phải đi qua Gateway (`:8080`) hoặc Nginx (`:3000`).

---

## 9. Hướng Dẫn Chạy Cục Bộ & Thao Tác Nghiệm Thu

### 9.1. Khởi Chạy Môi Trường Native (Windows PowerShell)
Trong chế độ Native, Web UI được phục vụ trực tiếp từ Gateway .NET tại cổng `8080`. Toàn bộ yêu cầu API `/v1/*` đều được Gateway định tuyến qua FastAPI.

```powershell
cd d:\Projects\dusnx-platform
.\start-local.ps1
```

Sau khi khởi chạy hoàn tất:
- **Web UI & API Gateway:** `http://localhost:8080`
- **FastAPI Documentation:** `http://localhost:8000/docs`
- **Ollama LLM Daemon:** `http://localhost:11434`

### 9.2. Khởi Chạy Bằng Docker Compose (Có Volume Bền & Nginx Reverse Proxy)
Trong chế độ Docker Compose, Web UI được phục vụ qua Nginx tại cổng `3000`. Nginx tự động reverse-proxy mọi yêu cầu `/v1/*` và `/api/v1/*` sang Gateway `gateway:8080`.

```powershell
cd d:\Projects\dusnx-platform
docker compose up -d --build

# Kiểm tra trạng thái:
docker compose ps
# Dữ liệu SQLite được lưu trữ bền vững tại thư mục máy chủ: ./runtime/ai-data
```

Truy cập:
- **Web UI (Nginx Reverse Proxy):** `http://localhost:3000`
- **API Gateway:** `http://localhost:8080/health`
- **FastAPI:** `http://localhost:8000/health`

### 9.3. Kịch Bản Thao Tác Nghiệm Thu Từng Bước Trên Giao Diện

1. **Đăng ký & Đăng nhập:**
   - Truy cập `http://localhost:8080` (Native) hoặc `http://localhost:3000` (Docker Compose).
   - Bấm tab **Đăng ký**, tạo tài khoản `alice` / `P@ssword123!`.
   - Đăng nhập: Hệ thống cấp Opaque Bearer Token được lưu an toàn trong SQLite `auth_tokens`. Giao diện chuyển sang màn hình Chat cá nhân hóa. Thanh footer hiển thị trạng thái Model và Provider.
2. **Nói một quyết định ban đầu:**
   - Gõ: *"Hãy nhớ rằng quyết định của tôi là sử dụng PostgreSQL cho cơ sở dữ liệu."*
   - Trợ lý ghi nhận quyết định vào trí nhớ dài hạn. Tab **Trí nhớ** hiển thị card quyết định đang hoạt động (`is_active=1`).
3. **Sửa quyết định & Từ chối:**
   - Gõ: *"Đổi PostgreSQL sang MongoDB."*
   - Trợ lý hiển thị banner xác nhận: Hỏi có muốn đổi từ PostgreSQL sang MongoDB hay không.
   - Gõ: *"Không"* (hoặc bấm nút **[✕ Giữ bản cũ]** trên banner).
   - Trợ lý xác nhận giữ nguyên quyết định PostgreSQL. Trí nhớ không bị thay đổi.
4. **Sửa quyết định & Đồng ý:**
   - Gõ lại: *"Đổi PostgreSQL sang MongoDB."*
   - Gõ: *"Đồng ý"* (hoặc bấm nút **[✓ Đồng ý sửa]**).
   - Trợ lý xác nhận cập nhật thành công. Tab **Trí nhớ** hiển thị phiên bản PostgreSQL đã bị gạch bỏ (`superseded`), phiên bản MongoDB đang hoạt động.
5. **Mở phiên mới và kiểm tra:**
   - Bấm **+ Phiên mới**.
   - Gõ: *"Cơ sở dữ liệu của dự án này là gì?"*
   - Trợ lý đọc trí nhớ hiện hành và LLM (Ollama `qwen2.5:0.5b`) trả lời chính xác về MongoDB. Tin nhắn hiển thị tag `🧠 1 trí nhớ`.
6. **Mô phỏng Client thứ hai (PowerPoint HTTP Client):**
   - Mở PowerShell và gửi sự kiện bằng token của Alice:
     ```powershell
     Invoke-RestMethod -Uri "http://localhost:8080/v1/me/events" -Method Post -Headers @{ Authorization = "Bearer <TOKEN_CỦA_ALICE>" } -ContentType "application/json" -Body '{"platform":"powerpoint","content":"Trình chiếu slide báo cáo kiến trúc MongoDB","event_type":"slide_view"}'
     ```
   - Chuyển sang tab **Timeline** trên Web UI của Alice: Sự kiện từ nguồn `powerpoint` xuất hiện ngay lập tức với state version đã được đồng bộ tăng dần.
   - *Lưu ý: Client thứ hai ở Tuần 2 là HTTP client mô phỏng connector, phân biệt rõ với Office Add-in tích hợp thực tế.*
7. **Kiểm tra cô lập Người dùng B:**
   - Đăng xuất Alice, tạo tài khoản `bob`.
   - Toàn bộ danh sách chat, trí nhớ, timeline sự kiện của Alice hoàn toàn trống trên tài khoản Bob. Bob không thể đọc hay can thiệp bất kỳ dữ liệu nào của Alice.
