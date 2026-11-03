# BÁO CÁO KIỂM CHỨNG TOÀN DIỆN, SỬA LỖI VÀ BÀN GIAO NỀN TẢNG DUSN-X TRÊN WINDOWS

- **Thời gian lập báo cáo:** 2026-11-03T08:40:00+07:00
- **Môi trường thực tế:** Windows 11 Native (`D:\Projects\dusnx-platform`), PowerShell 5.1
- **Python venv:** `python\.venv\Scripts\python.exe` (Python 3.12.8)
- **Node.js:** v24.13.0 | **.NET SDK:** 8.0.418
- **Ollama Windows:** v0.15.2 (Host `http://127.0.0.1:11434`, model phục vụ: `qwen2.5:0.5b`)
- **Repository:** `https://github.com/quocdoanhdang2-sketch/dusnx-platform`
- **Nhánh làm việc:** `feature/web-history-auth-hardening`
- **Baseline SHA:** `d11d4b3da51fd223b0c67e782ca5afb403def215`

---

## 1. TỔNG HỢP CÁC NGHI VẤN ĐÃ TÁI HIỆN, SỬA LỖI VÀ KIỂM CHỨNG HỒI QUY

| STT | Vấn đề / Nghi vấn | Trạng thái ban đầu & Tái hiện | Nguyên nhân gốc rễ (Root Cause) | Bản sửa mã nguồn | Kiểm chứng hồi quy (Regression Test) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **1** | **Harness song ngữ tự cộng pass vô điều kiện** | Trong `scripts/verify_bilingual_generation.py`, cuối vòng lặp các ca `CASE_11`, `CASE_12`, `CASE_13` có lệnh `linguistic_matched += 1` dù chưa kiểm tra nội dung reply. | Hardcoded counters được cộng thủ công trong hàm thực thi thay vì tính từ kết quả từng case. | Bỏ hoàn toàn các dòng cộng thủ công; viết hàm `compute_bilingual_summary(cases)` duyệt danh sách case đã hoàn thành để tính các số đo. | `python/tests/test_harness_contracts.py:test_failed_case_does_not_increment_success_counter` (PASSED). |
| **2** | **Trộn mẫu số đánh giá ngôn ngữ** | Template recall (`CASE_05`) và expected provider offline (`CASE_06`, `CASE_07`) bị tính vào mẫu số ngôn ngữ hoặc gán `linguistic_matched=True`. | Thiếu phân loại ranh giới giữa kiểm tra transport/contract và kiểm tra chất lượng dịch ngôn ngữ. | Gán rõ `case_type` và đánh dấu `linguistic_status="not_applicable"` cho template recall và lỗi provider kỳ vọng. Tách riêng `total_language_eligible_cases`. | `python/tests/test_harness_contracts.py:test_provider_offline_excluded_from_generation_and_language_denominators`, `test_template_recall_excluded_from_language_denominator` (PASSED). |
| **3** | **Exit code không phản ánh failure** | Script chạy đến cuối luôn thoát `sys.exit(0)` dù có case thất bại contract hoặc assertion. | Thiếu logic kiểm tra `summary["contract_failed"] > 0` trước khi exit. | Thêm `if summary["contract_failed"] > 0: sys.exit(1)`. Thêm tùy chọn `--strict-language` nếu muốn divergence ngôn ngữ cũng thoát mã 1. | `python/tests/test_harness_contracts.py:test_contract_failure_exits_nonzero` (PASSED). |
| **4** | **Backup/restore chưa chứng minh lịch sử dài** | Harness cũ chỉ tạo 3 tin nhắn và assert `len(messages) >= 3` nhưng báo cáo lại ghi "lịch sử dài >200 tin". | Dữ liệu synthetic test quá nhỏ, chưa kiểm chứng qua ranh giới phân trang (`limit=100`). | `scripts/verify_sqlite_backup_restore.py` tạo chính xác 205 tin nhắn (`msg-0000` đến `msg-0204`), backup qua SQLite Online Backup API, restore sang DB mới, duyệt 3 trang (100, 100, 5) đối chiếu 100% ID và nội dung. | Chạy trực tiếp `verify_sqlite_backup_restore.py`: Level 1 trả về `total_messages_restored=205`, `pagination_pages_fetched=3`, `messages_in_order=True`. |
| **5** | **Crash `KeyError` khi thiếu thư mục backup cá nhân** | Khi không có thư mục `backup-data-protected/`, hàm trả về dictionary thiếu khóa `integrity_passed`, gây `KeyError: 'integrity_passed'` ở hàm `main`. | Dictionary trả về khi thư mục vắng mặt chỉ có `{"status": "skipped", "reason": ...}` mà không có giá trị mặc định cho khóa `integrity_passed`. | Đã thêm khóa `"integrity_passed": None` và xử lý an toàn không crash; phân biệt rõ khi nào là skip do hạ tầng lab và khi nào là blocker bắt buộc. | `python/tests/test_harness_contracts.py:test_missing_protected_dir_handles_safely_without_keyerror` (PASSED). |
| **6** | **Trộn lẫn số liệu kiểm thử Office Mock và Web** | Báo cáo ghi chung "26 tests JavaScript pass", người đọc có thể nhầm là đã test trên ứng dụng PowerPoint Desktop Office 365. | Runner Node.js chạy chung các file test Web UI và taskpane test. | Tách bạch số liệu runner: 12 Web UI core + 5 Web UI Auth + 9 PowerPoint Mock. Ghi rõ bài test taskpane chạy trên môi trường giả lập in-memory `Office.js`, **chưa chứng minh trên PowerPoint Desktop thật**. | Ghi rõ trong bảng tổng hợp test và tài liệu bàn giao. |
| **7** | **Đánh giá heuristic ngôn ngữ chủ quan** | Text không dấu bị heuristic cũ coi là tiếng Anh; gán kết quả là "human review". | Hàm heuristic đơn giản hóa phân loại chuỗi ký tự. | Ghi nhận rõ trạng thái `uncertain` hoặc `divergent`, xuất nguyên văn output lỗi của model sub-1B, không tự điền kết quả người thật đánh giá. | `python/tests/test_harness_contracts.py:test_heuristic_treats_ambiguous_non_diacritic_text_as_uncertain` (PASSED). |

---

## 2. KẾT QUẢ KIỂM THỬ RUNNERS THỰC TẾ

```
========================= KẾT QUẢ TEST RUNNERS TỔNG HỢP =========================
1. Python Pytest (Core + Regressions):
   - Lệnh: python -m pytest python/tests -q --tb=short
   - Kết quả: 211 passed in 39.15s (205 core tests + 6 harness contract regression tests)
   - Exit code: 0

2. JavaScript Tests (Node Native Test Runner):
   - Lệnh: node --test web-ui/app.test.js web-ui/auth.test.js powerpoint-addin/taskpane.test.js
   - Web UI Core: 12 passed
   - Web Auth: 5 passed
   - PowerPoint Taskpane Mock: 9 passed
   - Tổng cộng: 26 passed (6 test suites)
   - Exit code: 0
   * LƯU Ý BẮT BUỘC: 9 test PowerPoint chỉ xác minh logic JavaScript và in-memory Office JS mock;
     chưa chứng minh trên ứng dụng desktop Office 365 / PowerPoint Desktop thật.

3. Gateway .NET Core Tests:
   - Lệnh: dotnet run --project gateway-dotnet.tests/Dusnx.Gateway.Tests.csproj -c Release
   - Kết quả: 7 / 7 passed
   - Exit code: 0

4. PowerShell Windows Local Health:
   - Lệnh: powershell -ExecutionPolicy Bypass -File scripts/tests/local-health.tests.ps1
   - Kết quả: 6 / 6 passed (Kiểm tra Web 5173, Gateway 5000, FastAPI 8000, Ollama 11434, SQLite WAL, Process isolation)
   - Exit code: 0

5. SQLite Backup/Restore Harness:
   - Lệnh: python scripts/verify_sqlite_backup_restore.py
   - Kết quả: Level 1 PASSED (205 messages verified in order, 3 pagination pages, idempotent retry preserved)
   - Exit code: 0

6. Bilingual Verification Harness:
   - Lệnh: python scripts/verify_bilingual_generation.py
   - Kết quả: Contract 13/13 PASSED, 10 eligible language cases (7 matched, 3 divergent)
   - Exit code: 0
================================================================================
```

---

## 3. MA TRẬN ĐÁNH GIÁ SONG NGỮ TRUNG THỰC (13 CASES)

Báo cáo đầy đủ dạng JSON được lưu trữ tại `docs/evidence/handover-20261102/bilingual_generation_report.json`.

| Mã ca (Case ID) | Loại ca (Type) | Prompt đầu vào | Kỳ vọng ngôn ngữ | Metadata thực tế | Trạng thái Contract | Đánh giá Heuristic | Human Review | Nội dung trả lời thực tế (Trích xuất) |
|---|---|---|:---:|---|:---:|:---:|:---:|---|
| `CASE_01_VI_PREF_VI` | `llm_generation` | "Hệ thống DUSN-X có những tính năng cốt lõi nào?" | vi | provider=ollama, source=llm | PASSED | matched | [ ] | *"Hệ thống DUSN-X có các tính năng chính bao gồm: 1. Mô phỏng và phân tích dữ liệu..."* |
| `CASE_02_EN_PREF_EN` | `llm_generation` | "What are the primary benefits of continuous integration in modern software engineering?" | en | provider=ollama, source=llm | PASSED | matched | [ ] | *"Continuous integration (CI) is a software development practice that involves the integration of code changes..."* |
| `CASE_03_VI_PREF_EN` | `llm_generation` | "Hãy giải thích ngắn gọn nguyên lý hoạt động của API Gateway." | en (input: vi) | provider=ollama, source=llm | PASSED | **divergent** | [ ] | Model 0.5B trả lời tiếng Việt: *"API Gateway là một hệ thống quản lý API..."* (Không tuân thủ yêu cầu dịch sang EN). |
| `CASE_04_EN_PREF_VI` | `llm_generation` | "Briefly explain why database indexing improves query performance." | vi (input: en) | provider=ollama, source=llm | PASSED | **divergent** | [ ] | Model 0.5B trả lời tiếng Anh: *"Database indexing improves query performance by allowing the database to quickly locate..."* (Bỏ qua pref=vi). |
| `CASE_05_AUTO_VI` | `llm_generation` | "Làm thế nào để duy trì sự tập trung hiệu quả khi làm việc từ xa?" | vi | provider=ollama, source=llm | PASSED | matched | [ ] | *"Duy trì sự tập trung hiệu quả khi làm việc từ xa có thể thay đổi theo từng công việc..."* |
| `CASE_06_AUTO_EN` | `llm_generation` | "How does public key cryptography secure internet communications?" | en | provider=ollama, source=llm | PASSED | matched | [ ] | *"Public key cryptography secures internet communications by enabling secure key exchange..."* |
| `CASE_07_VERBATIM_ENTITIES` | `verbatim_entities` | "Cấu hình URL https://api.dusnx.org/v1/auth và biến DUSNX_PORT=8088 trong file .env." | vi | provider=ollama, source=llm | PASSED | matched | [ ] | Bảo toàn chính xác `https://api.dusnx.org/v1/auth` và `DUSNX_PORT=8088`. |
| `CASE_08_MEMORY_RECALL_TEMPLATE` | `template_recall` | "Cụm máy chủ chọn công nghệ gì?" | vi | provider=local_template, source=template_memory | PASSED | not_applicable | [ ] | Trả về template từ trí nhớ đã lưu: *"Theo trí nhớ đang hiệu lực: chúng tôi chọn Kubernetes..."*. Không gọi LLM. |
| `CASE_09_AUTO_SHORT_HISTORY` | `llm_generation` | "Ưu điểm là gì?" (câu hỏi ngắn sau ngữ cảnh) | vi | provider=ollama, source=llm | PASSED | matched | [ ] | *"Ưu điểm là: Microservices giúp giảm tải hệ thống, tăng hiệu suất và dễ dàng quản lý..."* |
| `CASE_10_DURABLE_MEMORY_PREF_CHANGE` | `llm_generation` | Đổi pref sang EN, sau đó hỏi: "Hãy nêu 2 hệ điều hành phổ biến nhất." | en | provider=ollama, source=llm | PASSED | **divergent** | [ ] | Model 0.5B trả lời tiếng Việt: *"2.1 Windows: Được phát triển bởi Microsoft..."* theo ngôn ngữ câu hỏi. |
| `CASE_11_TWO_USERS_LANGUAGE_ISOLATION` | `user_preference_isolation` | User A (en) hỏi EN; User B (vi) hỏi VI. | A=en, B=vi | 2 calls riêng biệt, cô lập session | PASSED | matched | [ ] | User A nhận EN, User B nhận VI. Không rò rỉ cấu hình ngôn ngữ giữa các user. |
| `CASE_12_PROVIDER_OFFLINE` | `expected_provider_error` | Gửi prompt khi port Ollama offline (65534). | N/A | provider_ok=false, source=provider_error | PASSED | not_applicable | [ ] | Bắt lỗi kết nối thành công, không lưu lỗi thành tin nhắn trợ lý. |
| `CASE_13_MODEL_MISSING` | `expected_provider_error` | Gửi prompt với model không tồn tại ("nonexistent-model-xyz"). | N/A | provider_ok=false, source=provider_error | PASSED | not_applicable | [ ] | Bắt mã lỗi 404 từ Ollama thành công, không làm crash hệ thống. |

**Tóm tắt số đo ngôn ngữ:**
- Tổng số case: **13** | Contract Passed: **13/13** (100%)
- Real LLM Generations: **9** | Template Recall: **1** | Expected Provider Errors: **2** | Isolation: **1**
- Số ca đủ điều kiện đánh giá ngôn ngữ: **10**
  - **Matched:** **7 / 10** (70%)
  - **Divergent:** **3 / 10** (30% - Giới hạn mô hình nhỏ sub-1B khi dịch chéo)
  - **Uncertain:** **0 / 10**

---

## 4. XÁC MINH KHÔI PHỤC BACKUP SQLITE (205 MESSAGES QUA 3 TRANG)

Báo cáo JSON: `docs/evidence/handover-20261102/sqlite_backup_restore_report.json`.

1. **Level 1: Synthetic Backup & Restore (Chức năng toàn diện):**
   - Sinh chính xác **205 tin nhắn tuần tự** (`msg-0000` đến `msg-0204`).
   - Sao lưu online qua SQLite Online Backup API (`src.backup(dst)`).
   - Kiểm tra integrity trên file backup trả về `ok`.
   - Khôi phục sang thư mục mới `runtime/sqlite-backup-synthetic/restored/app_restored.db`.
   - Khởi động stack trên DB khôi phục:
     - Auth: Đăng nhập user và xác thực session thành công.
     - Phân trang: Đọc qua Cursor Pagination với `limit=100`:
       - Trang 1: 100 tin (`msg-0000` đến `msg-0099`).
       - Trang 2: 100 tin (`msg-0100` đến `msg-0199`).
       - Trang 3: 5 tin (`msg-0200` đến `msg-0204`).
       - **Tổng số: 205 tin nhắn, khớp 100% ID và nội dung, thứ tự tăng dần chuẩn xác, không rớt/lặp tin tại ranh giới trang.**
     - Trí nhớ: Bản ghi active được nạp, bản superseded bị loại trừ.
     - Retry: Replay idempotent receipt cũ không nhân đôi mutation.
   - **Trạng thái Level 1: PASSED**.

2. **Level 2: Protected Backup Integrity (Dữ liệu cá nhân):**
   - Kiểm tra toàn vẹn an toàn ở chế độ chỉ đọc: `auth.db` và `memory.db` trong `backup-data-protected/` đều đạt `integrity_check=ok` và `journal_mode=wal`.
   - Xử lý an toàn: Khi thư mục vắng mặt, script trả về `status="skipped"`, `integrity_passed=None`, không gây crash `KeyError`.
   - **Trạng thái Level 2: PASSED / SKIPPED AN TOÀN**.

---

## 5. RANH GIỚI VÀ CÁC PHẦN CHƯA HOÀN TẤT

1. **Khả năng dịch chéo ngôn ngữ của mô hình sub-1B:** `qwen2.5:0.5b` có xu hướng trả lời theo ngôn ngữ của câu hỏi thay vì chuyển sang ngôn ngữ đích trong trường hợp hỏi một thứ tiếng nhưng yêu cầu trả lời tiếng khác.
2. **Router nơ-ron thuần túy:** Đạt 63.6% Agent Accuracy và 36.4% Intent/Action Accuracy trên tập diagnostic 11 turns (`benchmarks/benchmark_v2_ai_diagnostic.jsonl`); hệ thống dựa vào bộ quy tắc nghiệp vụ (business rules) để bảo vệ quyết định.
3. **PowerPoint Desktop:** 9 test taskpane mới kiểm chứng trên môi trường giả lập in-memory `Office.js` của Node.js; chưa nghiệm thu sideload trên ứng dụng PowerPoint Desktop Office 365 thật.
4. **Môi trường Production:** Chưa thực hiện kiểm thử tải (load testing) hàng nghìn user đồng thời, chưa cấu hình SSL reverse proxy.

---

## 6. DANH MỤC TỆP BẰNG CHỨNG TRÊN GITHUB VÀ GÓI REVIEW OFFLINE

- **Báo cáo tổng thể:** `docs/HANDOVER_VERIFICATION_20261102.md`
- **Bảng review ngôn ngữ con người:** `docs/evidence/handover-20261102/bilingual_review_table.md`
- **Dữ liệu JSON 13 ca song ngữ:** `docs/evidence/handover-20261102/bilingual_generation_report.json`
- **Dữ liệu JSON Backup Restore:** `docs/evidence/handover-20261102/sqlite_backup_restore_report.json`
- **Dữ liệu JSON Router Diagnostic:** `docs/evidence/handover-20261102/router_diagnostic_report.json`
- **Gói Review Offline an toàn (ZIP):** `runtime/dusnx-review-package-20261102.zip` (SHA-256: `79d70274104b0626c7d80d698c7c6093ece260f06419e61bacef94ffbbf4c1bb`, 74,262 bytes).
