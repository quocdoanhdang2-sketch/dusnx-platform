# BÁO CÁO NGHIỆM THU TUẦN 1 — DUSN-X PLATFORM
**Commit kiểm tra & phát triển:** `4b82f53` → Hoàn thiện luồng Detect Confirm, Transaction Memory & State Persistence  
**Thời gian thực hiện:** 28/09/2026  
**Mục tiêu bắt buộc:** Khi người dùng sửa một quyết định, hệ thống chỉ ghi đè trí nhớ cũ sau một lời xác nhận đồng ý rõ ràng. Lời từ chối, câu mơ hồ, lỗi DB và yêu cầu từ tài khoản khác tuyệt đối không làm thay đổi quyết định đang có.

---

## 1. Sửa Phân loại Lời Xác nhận (Detect Confirm Classifier)

### Vấn đề trước khi sửa
- Code cũ kiểm tra substring đơn giản trên toàn bộ câu và kiểm tra danh sách `YES` trước `NO`.
- Gây lỗi nghiêm trọng: Các câu như `"không đồng ý"`, `"không xác nhận"`, `"không ok"`, `"không có"` bị bắt nhầm thành ĐỒNG Ý vì chứa từ con (`"đồng ý"`, `"xác nhận"`, `"ok"`, `"có"`). Ngoài ra các từ như `"nói"`, `"smoke"` có thể kích hoạt nhầm `"no"` hoặc `"ok"`.

### Giải pháp kỹ thuật đã triển khai
1. **Chuẩn hóa chuỗi (`_normalize_confirm_text` trong `python/apps/ai_api/main.py`)**:
   - Chuẩn hóa Unicode `NFC`.
   - Chuyển toàn bộ về chữ thường, thay thế toàn bộ dấu câu bằng khoảng trắng, co cụm khoảng trắng thừa.
2. **Nhận diện cụm từ và ranh giới từ (`\b...\b`)**:
   - **Từ chối (Rejection)**: Khớp các mẫu phủ định tiếng Việt và tiếng Anh có nghĩa rõ ràng:
     `không đồng ý`, `chưa đồng ý`, `không xác nhận`, `chưa xác nhận`, `không đúng`, `không được`, `không ok`, `đừng thay`, `đừng đổi`, `đừng sửa`, `giữ nguyên`, `thôi đừng thay`, `thôi đừng`, `không muốn thay`, `không cần thay`, `từ chối`, `bỏ qua`, `hủy`, `huỷ`, `cancel`, `thôi`, `đừng`, `no`, `nope`, `không`.
   - **Đồng ý (Confirmation)**: Loại bỏ các cụm phủ định trước khi xét mẫu đồng ý. Khớp chính xác:
     `có`, `đồng ý`, `xác nhận`, `ok`, `oke`, `okay`, `yes`, `yep`, `chuẩn`, `chính xác`, `thay đi`, `làm đi`, `tiến hành đi`, `chấp nhận`.
   - **Tín hiệu trái chiều / Không chắc chắn / Mơ hồ**:
     - Câu chứa cả tín hiệu đồng ý và từ chối (ví dụ: `"có nhưng mà đừng thay"`, `"ok nhưng thôi"`, `"đồng ý nhưng không muốn"`).
     - Cụm từ do dự/mơ hồ: `không chắc`, `chưa chắc`, `chưa rõ`, `chưa biết`, `phân vân`, `từ từ`, `suy nghĩ đã`, `khoan`, `hmm`.
     - Kết quả phân loại trả về `None` → Kích hoạt nhánh **Hỏi lại** và tuyệt đối không ghi đè trí nhớ.
3. **Đồng bộ giữa Chat và REST API**:
   - `POST /v1/pending-decisions/{id}/resolve` và nhánh chat xử lý pending decision đều đi qua cùng một hàm nghiệp vụ nguyên tử `resolve_pending_decision_atomic` trong `python/apps/ai_api/memory.py`.

---

## 2. Cập nhật Memory theo một Transaction Nguyên tử (Atomic Transaction)

### Giải pháp kỹ thuật (`resolve_pending_decision_atomic` trong `python/apps/ai_api/memory.py`)
- Mọi thao tác:
  1. Kiểm tra trạng thái pending decision còn `awaiting_confirm`.
  2. Xác minh quyền sở hữu (`user_id`).
  3. Kiểm tra memory cũ còn `is_active = 1`.
  4. Nếu memory cũ đã bị sửa/xóa trước đó: Đánh dấu pending là `stale` và trả về `(False, "stale")`.
  5. Cập nhật trạng thái pending thành `confirmed` (hoặc `rejected`).
  6. Vô hiệu hóa phiên bản cũ (`is_active = 0, superseded_by = new_id`).
  7. Tạo phiên bản mới (`version = old_version + 1`).
- Tất cả đều được bọc trong một khối transaction SQLite duy nhất (`with self._conn:`). Thành công toàn bộ hoặc tự động rollback toàn bộ.
- **Chống xác nhận 2 lần**: Lượt gọi thứ hai phát hiện trạng thái pending đã khác `awaiting_confirm` và trả về `False` (REST API trả về `404 Not Found`).
- **Bảo vệ chống lỗi DB**: Đã kiểm chứng bằng test mô phỏng trigger DB phát sinh lỗi. Trạng thái pending không bị cập nhật sai thành `confirmed` và bản ghi memory cũ vẫn giữ nguyên trạng thái `is_active = 1`.
- **Cô lập người dùng**: Người dùng B tuyệt đối không thể đọc hay resolve pending decision của Người dùng A.

---

## 3. Duy trì Trạng thái (State Persistence) và Tránh Test Rỗng

### Vấn đề trước khi sửa
- Khi xử lý pending decision (hỏi xác nhận, đồng ý, từ chối, mơ hồ), code cũ trả về `state_version=None` và không ghi nhận sự kiện vào DUSN-X state.
- Test cũ có điều kiện `if v1 is not None and v2 is not None:` khiến test có thể pass rỗng nếu cả hai đều là `None`.

### Giải pháp kỹ thuật
1. Bổ sung hàm `_advance_user_state(db, user_id, content, feedback_value)` cập nhật state DUSN-X ở mọi nhánh chat.
2. Mọi phản hồi chat đều trả về `state_version >= 1`.
3. Sửa toàn bộ assertions trong test: Bỏ mọi câu lệnh điều kiện `if ... is not None`, chuyển thành `assert resp["state_version"] is not None and resp["state_version"] >= 1`.
4. Bổ sung kiểm thử state giữa 2 user: Không chỉ so sánh số version mà còn kiểm tra các trường vector state và tính độc lập của lịch sử sự kiện.
5. Kiểm thử khởi động lại:
   - `test_state_survives_db_reopen`: Kiểm tra đóng và mở lại kết nối SQLite.
   - `test_state_survives_real_process_restart`: Chạy lại tiến trình Python thực tế (OS subprocess) trỏ vào cùng cơ sở dữ liệu và kiểm tra `state_version` tiếp tục tăng kế thừa từ trạng thái trước khi tắt.

---

## 4. Xác minh Dữ liệu Huấn luyện, Checkpoint và Cấu hình

### Kiểm tra Dữ liệu ("30k VALID")
- File dữ liệu: `data/synthetic_30k_v2.jsonl`
- Số lượng: 30,000 dòng JSON tổng hợp, sinh ra từ 1,000 người dùng nhân tạo (mỗi người dùng đúng 30 sự kiện theo thời gian).
- Chạy công cụ kiểm tra dữ liệu:
  ```powershell
  python scripts/validate_data.py --data data/synthetic_30k_v2.jsonl
  ```
  **Kết quả:** 30,000 dòng hợp lệ theo schema.
- **Lưu ý minh bạch:** "30k VALID" chỉ là kết quả kiểm tra tính toàn vẹn của dữ liệu mẫu tổng hợp (synthetic data validation). Đây **KHÔNG** phải là kết quả của một mô hình học máy đã hoàn thành huấn luyện trên dữ liệu thực tế.

### Kiểm tra Checkpoint và Metrics
- Model config: `configs/smoke_v2.yaml` (sequence_len=8, stride=4, batch_size=8, vocab_size=16384).
- Checkpoint API nạp thực tế khi khởi động: `artifacts/dusnx_smoke_v2.pt` (Kích thước: 8,009,997 bytes).
- File metrics: `artifacts/dusnx_smoke_v2.metrics.json` ghi nhận:
  - Dataset SHA-256: `05dcda691ba5a94a9052022e5bac93ae4426305ae0069f345d2159e02055df2c`
  - Feedback contract: `previous_event_feedback_v1`
  - Phân chia: 800 train users, 100 validation users, 100 test users.
  - Kết quả test đánh giá trên tập test (100 synthetic users):
    - `loss`: 0.00234
    - `intent_macro_f1`: 1.0
    - `router_macro_f1`: 1.0
    - `next_action_macro_f1`: 1.0
- Lệnh chạy huấn luyện lại khi cần:
  ```powershell
  $env:PYTHONPATH="python/src;python/apps;python;."
  python python/scripts/train.py --config configs/smoke_v2.yaml
  ```

### Kiểm tra Cấu hình Môi trường (.env.example)
- Đã đối soát toàn bộ các biến môi trường giữa `.env.example` và code trong `auth.py`, `provider.py`, `main.py`, Gateway:
  - `DUSNX_TOKEN_TTL_SECONDS` và `DUSNX_TOKEN_TTL_HOURS` được hỗ trợ đồng thời.
  - `DUSNX_OPENAI_BASE_URL` (kèm fallback `DUSNX_OPENAI_URL`), `DUSNX_OPENAI_API_KEY` (kèm fallback `DUSNX_OPENAI_KEY`).
  - `DUSNX_OLLAMA_TIMEOUT` và `OLLAMA_TIMEOUT`.
  - Hỗ trợ bí danh provider `openai_compatible`.

### Kiểm tra Thực tế LLM Provider
- Kiểm tra tiến trình Ollama cục bộ: `ollama list` báo lỗi khởi tạo daemon (`Unable to init instance`), chưa có dịch vụ nền lắng nghe trên `http://localhost:11434`.
- Chưa cấu hình OpenAI API Key thật từ xa.
- Hệ thống đã kiểm thử luồng fallback: Trả lời thông báo lỗi mềm có cấu trúc `[Ollama không khả dụng: ...]`, cờ `provider_ok=False`, không gây crash API hay mất mát state.

---

## 5. Kết quả Kiểm thử Tổng thể (Test Suite Execution)

| Thành phần | Lệnh thực thi | Kết quả | Ghi chú |
| :--- | :--- | :--- | :--- |
| **Python Test Suite** | `pytest python/tests -v --tb=short` | **71/71 PASS (100%)** | Bao gồm 26 test HTTP integration mới và nâng cấp |
| **.NET Gateway Tests** | `dotnet run --project gateway-dotnet.tests/Dusnx.Gateway.Tests.csproj` | **7/7 PASS (100%)** | Kiểm tra lịch sử, JSONL append, snake_case, cô lập user |
| **Web UI Tests** | `node --test web-ui/app.test.js` | **9/9 PASS (100%)** | Kiểm tra chống XSS, memory card, chat bubble |
| **Local Health Check** | `powershell -File ./scripts/tests/local-health.tests.ps1` | **2/2 PASS (100%)** | Kiểm tra endpoint sức khỏe và khởi động |
| **Data Validator** | `python scripts/validate_data.py --data data/synthetic_30k_v2.jsonl` | **30,000/30,000 PASS** | 1,000 users hợp lệ |
| **Python Bytecode Compile** | `python -m compileall -q python` | **PASS (Mã sạch)** | Không có lỗi cú pháp |

---

## 6. Hạng mục Đã đo được vs. Chưa đo được

### Đã đo được (Measured & Verified)
1. **Phân loại xác nhận**: Đã kiểm thử tự động với các câu:
   - Từ chối: `"không đồng ý"`, `"không xác nhận"`, `"không đúng"`, `"đừng thay"`, `"không, giữ nguyên"`, `"cancel"`, `"no"`.
   - Đồng ý: `"có"`, `"đồng ý"`, `"xác nhận"`, `"ok"`, `"yes"`.
   - Mơ hồ / Trái chiều: `"hmm không chắc"`, `"có nhưng mà đừng thay"`, `"đồng ý nhưng thôi"` → Đều hỏi lại mà không thay đổi memory.
2. **Tính bất biến của Memory khi bị từ chối**: Phiên bản active cũ giữ nguyên 100%, không sinh version mới khi người dùng từ chối.
3. **Transaction nguyên tử & Rollback**: Mô phỏng trigger SQLite lỗi khi cập nhật bản ghi cũ → Bản ghi mới không được lưu, pending không bị cập nhật sai, toàn bộ giao dịch rollback hoàn hảo.
4. **Cô lập người dùng**: Người dùng B không thể đọc, cập nhật, xóa memory hay resolve pending của Người dùng A.
5. **Độ bền của State**: `state_version` tăng đều đặn qua các lượt chat, không trả về `None`, sống sót qua việc đóng/mở DB và qua khởi động lại tiến trình Python độc lập.

### Chưa đo được (Unmeasured & Transparent Caveats)
1. **Dữ liệu thật của người dùng cuối (Real-world Data Distribution)**: Model hiện tại (`dusnx_smoke_v2.pt`) chỉ được huấn luyện và đánh giá trên bộ dữ liệu tổng hợp (synthetic 30k). Độ chính xác phân loại ý định trên ngôn ngữ tự nhiên đa dạng của người dùng thực tế chưa được đo lường qua benchmark độc lập.
2. **Hiệu năng và độ trễ LLM thực tế**: Do môi trường hiện tại chưa khởi chạy daemon Ollama / GPU LLM và chưa có API key bên ngoài, độ trễ sinh từ (time-to-first-token, generation tokens/sec) chưa được đo lường thực tế.
3. **Tải đồng thời cao (High Concurrency / Stress Testing)**: Hệ thống sử dụng SQLite với WAL mode; giới hạn chịu tải khi hàng ngàn kết nối ghi đồng thời chưa được đo bằng công cụ tải trọng như Locust hoặc k6.

---

## 7. Lệnh Tái hiện Kiểm thử Độc lập

```powershell
# 1. Kích hoạt môi trường và chạy toàn bộ Python tests
$env:PYTHONPATH="python/src;python/apps;python;."
python -m pytest python/tests -v --tb=short

# 2. Chạy kiểm thử Gateway .NET
dotnet run --project gateway-dotnet.tests/Dusnx.Gateway.Tests.csproj

# 3. Chạy kiểm thử Web UI
node --test web-ui/app.test.js

# 4. Kiểm tra sức khỏe dịch vụ
powershell -File ./scripts/tests/local-health.tests.ps1

# 5. Kiểm tra dữ liệu synthetic 30k
python scripts/validate_data.py --data data/synthetic_30k_v2.jsonl
```
