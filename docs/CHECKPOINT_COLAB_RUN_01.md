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

### B. Phân tích nguyên nhân & Thiết kế sửa chất lượng trí nhớ (Memory Quality Redesign)

#### 1. Nguyên nhân gốc rễ của lỗi lưu "AWS nhé." và "AWS nhé..":
1. **Bóc tách đề xuất thô bạo bằng Regex:** Đoạn mã cũ sử dụng `re.sub(r"^.+?(?:thành|sang|bằng|to|with|use|dùng)\s+", "", req.message)` để lấy nội dung mới. Khi người dùng nói *"Đổi quyết định hạ tầng đám mây sang AWS nhé"*, regex này cắt bỏ toàn bộ phần trước `sang `, chỉ giữ lại đúng mẩu vụn `"AWS nhé."`.
2. **Khớp chuỗi thay thế bị trượt (Mismatched Substring):** Logic cũ cố gắng tìm `target_word` (ở đây là `"quyết định hạ tầng đám mây"`) trong nội dung bản ghi cũ. Tuy nhiên, bản ghi cũ lưu *"chúng tôi chọn GCP cho dự án hạ tầng đám mây năm 2026"* (không chứa nguyên văn cụm từ *"quyết định hạ tầng đám mây"*). Do đó, phép thay thế chuỗi không thực hiện được và hệ thống fallback lưu mẩu câu vụn `"AWS nhé."`.
3. **Lặp dấu câu (`..`) do nối chuỗi thiếu kiểm tra:** `grounding.py` luôn nối thêm dấu chấm `.` vào cuối câu trả lời. Khi mẩu câu `"AWS nhé."` đã có sẵn dấu chấm ở cuối, kết quả trở thành `"AWS nhé.."`.

#### 2. Thiết kế sửa tổng quát (Không hardcode thực thể hay câu mẫu):
- **Bóc tách đa thành phần (`decision_updater.py`):**
  - Tách bạch: `topic` (chủ đề/phạm vi, ví dụ: `"hạ tầng đám mây"`), `new_value` (giá trị mới sau khi dọn sạch trợ từ tiếng Việt như *nhé, nha, ạ, đi, nhá*: `"AWS"`), `raw_target` và `statement_source`.
  - Mở rộng bảng `pending_decision_updates` với các cột `topic`, `new_value`, `statement_source` (kèm migration tự động).
- **Tổng hợp câu quyết định hoàn chỉnh (`synthesize_full_decision`):**
  - Tự động nhận diện cấu trúc vị ngữ/thực thể của câu cũ (ví dụ: `chúng tôi chọn [GCP] cho [dự án hạ tầng đám mây năm 2026]`) để thay thế thực thể cũ bằng thực thể mới, bảo toàn đầy đủ chủ ngữ, bổ ngữ, phạm vi và mốc thời gian:
    *Cũ:* `chúng tôi chọn GCP cho dự án hạ tầng đám mây năm 2026`
    *Mới:* `chúng tôi chọn AWS cho dự án hạ tầng đám mây năm 2026`
- **Xử lý mơ hồ khi có nhiều bản ghi phù hợp (`find_best_matching_decision`):**
  - So khớp theo từ khóa chủ đề (bỏ qua từ dừng và từ lệnh).
  - Nếu có 2 hoặc nhiều quyết định cùng loại và câu nói không đủ thông tin phân biệt, hệ thống hỏi lại để làm rõ chứ **không tự ý chọn bừa** một bản ghi.
- **Supersede nguyên tử & Idempotent Retry (`memory.py`):**
  - Chỉ supersede khi người dùng xác nhận rõ ràng. Nếu từ chối hoặc trả lời mơ hồ, bản ghi cũ được giữ nguyên vẹn 100%.
  - Cập nhật bản ghi cũ (`is_active = 0`, `superseded_by = new_id`) và tạo bản ghi mới (`version = old.version + 1`, `is_active = 1`) trong cùng một SQLite transaction duy nhất dưới lock bảo vệ.
  - Hỗ trợ retry idempotent: tránh tạo version trùng lặp khi người dùng gửi lại request xác nhận.
- **Chuẩn hóa sinh câu trả lời (`grounding.py`):**
  - `format_memory_answer`: dọn sạch dấu câu thừa ở cuối (`re.sub(r"[.?!,;:]+$", "", c)`) trước khi thêm dấu chấm duy nhất, triệt tiêu hoàn toàn lỗi dấu `..`.
  - `is_memory_question`: bao quát các động từ lựa chọn/quyết định (`chọn`, `quyết định`, `lựa chọn`, `dùng`, `sử dụng`, `hiện tại`, v.v.).

---

### C. Kết quả nghiệm thu thực tế qua Gateway với Checkpoint Colab & Ollama thật

Kịch bản nghiệm thu thực tế qua Gateway (cổng `8080`) với người dùng mới (`user_quality_53052feaaf46`):
1. **Lưu 2 quyết định độc lập khác chủ đề trong Phiên 1:**
   - Quyết định 1 (Hạ tầng): *"chúng tôi chọn GCP cho dự án hạ tầng đám mây năm 2026"*
   - Quyết định 2 (Cơ sở dữ liệu): *"chúng tôi chọn PostgreSQL làm hệ thống cơ sở dữ liệu chính"*
2. **Yêu cầu sửa 1 quyết định:**
   - Người dùng: *"Đổi quyết định hạ tầng đám mây sang AWS nhé"*
   - Pending record tạo ra:
     - `topic`: `"hạ tầng đám mây"`
     - `new_value`: `"AWS"`
     - `old_content`: `"chúng tôi chọn GCP cho dự án hạ tầng đám mây năm 2026"`
     - `proposed_content`: `"chúng tôi chọn AWS cho dự án hạ tầng đám mây năm 2026"` (Câu đầy đủ, chuẩn ngữ pháp, không còn là `"AWS nhé."`)
   - Trợ lý phản hồi:
     > *"Tôi thấy bạn muốn thay đổi quyết định. Bạn có muốn:*
     > ***Cũ:*** *chúng tôi chọn GCP cho dự án hạ tầng đám mây năm 2026*
     > ***Mới:*** *chúng tôi chọn AWS cho dự án hạ tầng đám mây năm 2026*
     > *Trả lời **Có** để xác nhận hoặc **Không** để huỷ."*
3. **Xác nhận cập nhật:**
   - Người dùng: *"Đồng ý"*
   - Bản ghi cũ (GCP) được supersede nguyên tử sang `is_active = false`, `superseded_by = f263182549f0eec2c20568c89da15f0b`.
   - Bản ghi mới (AWS) được kích hoạt `is_active = true`, `version = 2`.
   - Bản ghi cơ sở dữ liệu (PostgreSQL) giữ nguyên `is_active = true`, `version = 1`.
4. **Mở phiên mới (Phiên 2) & Hỏi riêng từng quyết định:**

| Câu hỏi | Câu trả lời nguyên văn | `provider_used` | `model_used` | `routing_source` | `memory_ids_used` | Trạng thái kiểm chứng |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **"Hạ tầng đám mây được chọn cho dự án là gì?"** | *"Theo trí nhớ đang hiệu lực: chúng tôi chọn AWS cho dự án hạ tầng đám mây năm 2026."* | `ollama` | `qwen2.5:0.5b` | `model` | `["f263182549f0...", "d6cd8284d3b2..."]` | **AWS là quyết định hiện hành, không nhắc GCP, không có dấu `..`** |
| **"Cơ sở dữ liệu được chọn là gì?"** | *"Theo trí nhớ đang hiệu lực: chúng tôi chọn PostgreSQL làm hệ thống cơ sở dữ liệu chính."* | `ollama` | `qwen2.5:0.5b` | `model` | `["d6cd8284d3b2...", "f263182549f0..."]` | **PostgreSQL là quyết định hiện hành, không bị nhầm với hạ tầng đám mây** |

5. **Trạng thái Database SQLite (`python/data/memory.db`):**

| ID | Content | info_type | is_active | superseded_by | version | Trạng thái |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `c0c7abb2b541...` | chúng tôi chọn GCP cho dự án hạ tầng đám mây năm 2026 | `decision` | **`0`** | `f263182549f0...` | 1 | **Superseded (Không còn hiệu lực)** |
| `f263182549f0...` | chúng tôi chọn AWS cho dự án hạ tầng đám mây năm 2026 | `decision` | **`1`** | `NULL` | 2 | **Active (Đang hiệu lực - Đầy đủ nội dung)** |
| `d6cd8284d3b2...` | chúng tôi chọn PostgreSQL làm hệ thống cơ sở dữ liệu chính | `decision` | **`1`** | `NULL` | 1 | **Active (Đang hiệu lực - Độc lập)** |

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
