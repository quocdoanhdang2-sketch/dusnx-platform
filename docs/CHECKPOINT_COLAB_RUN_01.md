# Báo Cáo Tích Hợp Checkpoint Colab Run 01 (DUSN-X Router)

## 1. Thông Tin Checkpoint & Môi Trường Huấn Luyện

| Thuộc tính | Giá trị thực tế |
| :--- | :--- |
| **Commit mã nguồn huấn luyện** | `50e1042aa45ca99d17c989817a08a0896f7a7935` |
| **Phần cứng huấn luyện** | Google Colab Tesla T4 GPU (CUDA 12.8, PyTorch 2.11.0, Python 3.13.15) |
| **Đường dẫn checkpoint cục bộ** | `training-results/colab-run-01/extracted/dusnx-router-full-01/router.pt` |
| **SHA-256 Checkpoint** | `56f56e6d61afc264fb02d690d2872fb3ac5db9749a659c8493fd9d99eab7e7b1` |
| **Tổng số epoch** | 8 epochs (dừng sớm với patience=3 tại epoch 8) |
| **Best Epoch** | **Epoch 6** |
| **Điểm Validation tốt nhất** | **0.8062** (Macro-F1 trung bình cả 3 đầu phân loại) |
| **Validation Intent Macro-F1** | 0.7453 |
| **Validation Router Macro-F1** | 0.8746 |
| **Validation Next Action Macro-F1** | 0.7987 |
| **Tập dữ liệu Train** | 371 chuỗi, 4.185 sự kiện (trong đó 3.000 event legacy lặp nhiều từ template tổng hợp cũ + 1.185 event thiết kế mới đa lượt) |
| **Tập dữ liệu Validation** | 46 chuỗi, 203 sự kiện (24 template families, 0% overlap với train và các tập holdout) |

---

## 2. Hợp Đồng Kiến Trúc & Kiểm Tra Tương Thích (Schema Verification)

Checkpoint đã được kiểm tra bằng hàm `validate_checkpoint_compatibility()` tại [`python/src/dusnx_core/checkpoint.py`](file:///d:/Projects/dusnx-platform/python/src/dusnx_core/checkpoint.py):
- **Kích thước từ vựng (Vocab size):** 16.384 token
- **Chiều vector token (Token dim):** 96
- **Chiều không gian nền tảng (Platform dim):** 24 (Web, PowerPoint, VS Code)
- **Chiều sự kiện (Event type dim):** 8
- **Kích thước Recurrent State:**
  - `global_state_dim`: 160
  - `platform_state_dim`: 112
  - `task_state_dim`: 112
  - **Combined State Dimension:** 384 (160 + 112 + 112)
- **Từ vựng nhãn phân loại:**
  - `INTENTS` (6): `chat`, `research`, `summarize`, `presentation_edit`, `recommendation`, `followup`
  - `AGENTS` (3): `conversation`, `search_rag`, `productivity`
  - `NEXT_ACTIONS` (6): `reply`, `search`, `summarize`, `edit_slide`, `recommend`, `clarify`

---

## 3. Cách Cấu Hình & Khởi Động Native Stack Trên Máy Cục Bộ

### Cấu hình biến môi trường qua PowerShell
Đường dẫn checkpoint được cấu hình linh hoạt qua biến môi trường hoặc tự động nhận diện từ thư mục `training-results`:
```powershell
# Tuỳ chọn: chỉ định rõ đường dẫn checkpoint (tương đối hoặc tuyệt đối)
$env:DUSNX_CHECKPOINT = "training-results\colab-run-01\extracted\dusnx-router-full-01\router.pt"
$env:DUSNX_DEVICE = "auto"
```

### Lệnh khởi động tự động toàn bộ dịch vụ (Runbook)
```powershell
powershell -ExecutionPolicy Bypass -File .\start-local.ps1
```

Script thực hiện các bước kiểm tra và khởi động chuẩn hóa:
1. **Chuẩn hóa đường dẫn checkpoint:** Chuẩn hóa biến `$env:DUSNX_CHECKPOINT` thành đường dẫn tuyệt đối (`[System.IO.Path]::GetFullPath`) trước khi nạp vào tiến trình FastAPI từ thư mục `python/`.
2. **Kiểm tra tiến trình cổng 8000 tức thời (`Assert-DusnxFastApiCheckpoint`):**
   - Nếu cổng 8000 đã có tiến trình FastAPI lắng nghe, script probe ngay `/health` trong 3 giây.
   - Nếu checkpoint đang nạp khác với checkpoint được yêu cầu, script **dừng ngay lập tức** và thông báo chi tiết:
     - PID và tên tiến trình đang chạy (ví dụ: `PID 24716, python`).
     - Đường dẫn checkpoint đang nạp (`Loaded checkpoint`) vs đường dẫn được yêu cầu (`Requested checkpoint`).
     - Câu lệnh PowerShell cụ thể để tắt tiến trình cũ: `Stop-Process -Id <PID> -Force`.
   - **Tuyệt đối không chờ 60 giây** rồi báo lỗi chung, và **không tự ý dừng các tiến trình** chưa xác minh thuộc DUSN-X.
3. **Khởi chạy .NET 8 Gateway** trên cổng `8080` (nếu chưa chạy).
4. **Kiểm tra sức khỏe toàn hệ thống (`Wait-DusnxHttpService`)** đảm bảo `runtime_mode = "trained_dusnx"` và `checkpoint_loaded = true`.
5. **Mở Web UI tại `http://127.0.0.1:8080`.**

---

## 4. Bằng Chứng Thực Tế (Health & Web Flow)

### A. Phản hồi thực tế từ `/health` (FastAPI & Gateway)
```json
{
  "status": "ok",
  "device": "cpu",
  "runtime_mode": "trained_dusnx",
  "checkpoint": "D:\\Projects\\dusnx-platform\\training-results\\colab-run-01\\extracted\\dusnx-router-full-01\\router.pt",
  "checkpoint_loaded": true,
  "checkpoint_path": "D:\\Projects\\dusnx-platform\\training-results\\colab-run-01\\extracted\\dusnx-router-full-01\\router.pt",
  "model_loaded": true,
  "provider_ok": true,
  "model_version": "checkpoint:router.pt:sha256-56f56e6d61af:config-03b14389ce98",
  "metadata": {
    "epoch": 6,
    "best_val_score": 0.8061977767812536,
    "commit_sha": "50e1042aa45ca99d17c989817a08a0896f7a7935",
    "train_samples": 3814,
    "validation_samples": 157
  },
  "provider": {
    "provider": "ollama",
    "model": "qwen2.5:0.5b",
    "available": true,
    "base_url": "http://localhost:11434"
  }
}
```

### B. Luồng tương tác người dùng qua Gateway (Port 8080)
1. **Đăng ký tài khoản thử nghiệm mới:** Tạo user mới `user_real_1790710227` (`ea01af6681ad3ec2b947f40857f78fa7`), nhận Bearer token và xác thực qua Gateway `/v1/auth/login`.
2. **Lưu quyết định trong Phiên 1:**
   - Người dùng: *"Ghi nhớ quyết định: Chúng tôi chọn GCP cho dự án hạ tầng đám mây năm 2026."*
   - Router & State: Ghi nhận sự kiện `memory_create`, lưu bản ghi quyết định với trạng thái `active` (`is_active = 1`).
3. **Sửa quyết định có xác nhận (Confirmation Guard):**
   - Người dùng: *"Đổi quyết định hạ tầng đám mây sang AWS nhé."*
   - Router & State: Nhận diện `decision_modify_intent` -> tạo `pending_decision` và sinh phản hồi xác nhận:
     > *"Tôi thấy bạn muốn thay đổi quyết định. Bạn có muốn: Cũ: GCP... Mới: AWS... Trả lời Có để xác nhận hoặc Không để huỷ."*
   - Người dùng: *"Có, tôi xác nhận đổi."*
   - Router & State: Nhận diện xác nhận, cập nhật quyết định nguyên tử trong SQLite (thay thế GCP bằng AWS).
4. **Mở phiên mới (Phiên 2) & Hỏi lại quyết định hiện hành:**
   - Mở Session 2 hoàn toàn mới (`25ce105f64b8a245d8b76c8c4a1b0c03`).
   - Người dùng: *"Quyết định hạ tầng đám mây năm 2026 hiện hành của tôi là gì?"*

### C. Kết quả chạy thực tế với Ollama thật (`qwen2.5:0.5b`) & Kiểm chứng Database

**1. Phản hồi nguyên văn từ Gateway (Phiên mới):**
> *"Theo trí nhớ đang hiệu lực: AWS nhé.."*

**2. Chi tiết trường dữ liệu trả về từ API:**
- **`provider_used`:** `ollama` (Không dùng mock)
- **`model_used`:** `qwen2.5:0.5b`
- **`provider_ok`:** `true`
- **`routing_source`:** `model` (được định tuyến bởi checkpoint Colab T4 `router.pt`)
- **`runtime_mode`:** `trained_dusnx`
- **`memory_ids_used`:** `["ba73a5ad07889fb02b3182e033ef55ba"]`

**3. Trạng thái cơ sở dữ liệu SQLite (`python/data/memory.db`):**

| ID | Content | info_type | is_active | superseded_by | version | Trạng thái |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `70ff685933fe9a071dbd7561f3014a60` | Chúng tôi chọn GCP cho dự án hạ tầng đám mây năm 2026 | `decision` | **`0`** | `ba73a5ad07889fb02b3182e033ef55ba` | 1 | **Superseded (Không hiệu lực)** |
| `ba73a5ad07889fb02b3182e033ef55ba` | AWS nhé. | `decision` | **`1`** | `NULL` | 2 | **Active (Đang hiệu lực)** |

**4. Xác nhận kết quả:**
- **AWS là quyết định hiện hành duy nhất.**
- **GCP đã bị thay thế hoàn toàn (`is_active = 0`, `superseded_by = ...`) và không bị trình bày như quyết định hiện hành.**
- **Ollama thật (`qwen2.5:0.5b`) hoàn thành câu trả lời dựa trên context được ground từ active memory.**

---

## 5. Phân Định Rõ Ràng & Giới Hạn Của Checkpoint

### Phân định giữa DUSN-X Router và LLM Provider:
- **Phần do DUSN-X Recurrent State & Router đảm nhiệm:**
  - Duy trì vector trạng thái ẩn đa chiều (`global`, `platform`, `task`).
  - Định tuyến tác vụ (agent: conversation, search_rag, productivity).
  - Dự đoán hành động tiếp theo (next action: reply, search, clarify, summarize, edit_slide).
  - Quản lý trạng thái quyết định chờ duyệt (`await_confirm`) và bảo toàn ngữ cảnh qua nhiều phiên.
- **Phần do LLM Provider (Ollama / OpenAI) đảm nhiệm:**
  - Sinh văn bản tự nhiên theo ngữ cảnh.
  - Khi Ollama ngoại tuyến hoặc không chạy được trên máy: Hệ thống trả về thông báo minh bạch `[Ollama không khả dụng: Connection refused]`. Các tầng state tracking, routing và memory retrieval hoàn toàn không bị gián đoạn hay phụ thuộc vào sự tồn tại của LLM.

### Các giới hạn cần lưu ý:
1. **Không phải mô hình LLM:** Checkpoint này là mạng nơ-ron hồi quy nhỏ (state updater + router heads) phục vụ định tuyến và cập nhật trạng thái; không dùng để sinh văn bản tự do.
2. **Không phải mô hình đa phương thức:** Checkpoint không có khả năng hiểu ảnh, không có mô-đun quản lý lịch biểu hay mô phỏng tính cách toàn diện.
3. **Đánh giá trên Holdout v2 (Chẩn đoán):**
   - Holdout v2 là tập chẩn đoán đã xem kết quả trước đó. Điểm số với provider=mock trên v2 chỉ mang tính chất kiểm tra kỹ thuật, không được coi là chất lượng trợ lý ngoài thực tế.
   - Trên v2, 23/38 lượt mang nhãn nghiệp vụ bộ nhớ (`memory_create`, `decision_update`) thuộc tầng ứng dụng bên trên, nằm ngoài từ vựng phân loại của neural router.
   - Hệ thống Full Hybrid DUSN-X hiện chưa thể hiện ưu thế vượt trội rõ rệt so với baseline không trạng thái (no-state) trên tập v2.
4. **Cam kết bảo lưu Holdout v3:**
   - Tập `holdout_v3` (311 events, SHA-256 `094268aa...`) **tuyệt đối chưa được chạy** với bất kỳ checkpoint, mô hình, rule hay baseline nào. Tập này được niêm phong hoàn toàn để phục vụ đánh giá độc lập sau này.
