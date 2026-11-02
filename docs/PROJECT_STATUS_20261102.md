# DUSN-X — kiểm tra và cải thiện ngày 02/11/2026

Mục tiêu: Web chatbot có đăng nhập, session, trí nhớ, router đã train và generation
qua Gateway → FastAPI → Ollama. Người dùng cho phép lấy mục tiêu trong repo làm
chuẩn và bổ sung cải thiện có căn cứ. Baseline: `b8c0a710c4bb8c786669eadc6576b352915e5ed8`.
Đây là kiểm chứng cloud Linux hiện tại; báo cáo Windows trước đây là bằng chứng
lịch sử. Nhánh bàn giao: `feature/web-history-auth-hardening`; không merge main
hoặc deploy trong đợt này. SHA và kết quả push được xác minh trong thông báo bàn giao.

## Đã xác minh và sửa

| Thành phần | Kết quả hiện tại |
|---|---|
| Router người dùng cung cấp | SHA-256 `56f56e6d61afc264fb02d690d2872fb3ac5db9749a659c8493fd9d99eab7e7b1` khớp tài liệu. Strict load đạt; trọng số hữu hạn. Giữ nguyên file đính kèm, sao chép vào đường dẫn runtime được ignore. |
| Router qua Gateway | `/v1/health` trả `checkpoint_loaded=true`, `runtime_mode=trained_dusnx`, model version `checkpoint:router.pt:sha256-56f56e6d61af:config-03b14389ce98`. |
| Lịch sử chat dài | Sửa lỗi mở lại phiên chỉ hiện 100 tin đầu tiên. Web hiện mở 100 tin mới nhất và có nút xem tin cũ. Cursor theo message ID, kiểm tra owner/session, không bị dịch trang khi có tin mới. Endpoint list cũ được giữ để tương thích. |
| Chuyển phiên/đăng xuất | Bỏ phản hồi lịch sử đã lỗi thời; reset nút tải cũ và banner xác nhận khi đổi phiên; chặn gửi trong khi đang tải để tránh hiển thị trùng. Pending-decision response cũng được kiểm tra phiên tải hiện tại. |
| Trí nhớ và vận hành | Runtime HTTP/Chromium/SQLite xác minh active/supersede, cách ly user/project, clarification, retry, lỗi ghi DB, backup/restore và startup lỗi. |
| Web và Gateway | HTML được Gateway phục vụ, HTTP 200. .NET build và 7/7 Gateway tests đã đạt trong phiên thiết lập; code Gateway không thay đổi trong đợt cải thiện. |

Không sửa trọng số, dữ liệu/gold/attestation hoặc train lại model. Checkpoint router
không phải LLM sinh văn bản. Điểm validation 0,8062 là metadata được lưu trong file,
không phải điểm đánh giá mới. Chưa có log từng epoch để kết luận overfitting.

## Sửa bổ sung theo yêu cầu kiểm tra bằng harness

- Chromium tái hiện trước sửa: `registerForm` có thuộc tính `hidden` nhưng vẫn
  nhìn thấy. Nguyên nhân: `.auth-form { display:flex }` ghi đè display mặc định
  của trình duyệt. Thêm quy tắc `[hidden] { display:none !important }`; kiểm tra
  lại hai tab bằng Chromium thật, mỗi lần chỉ form được chọn hiển thị.
- Bốn regression JavaScript được chạy trước sửa đều thất bại: logout chưa xóa
  auth trước khi mạng trả về; login trả muộn khôi phục phiên đã logout; 401 cũ
  xóa token mới; body giải mã muộn trả dữ liệu phiên cũ. Đã thêm generation/token
  guard trước và sau khi đọc response body, xóa state cục bộ ngay khi logout,
  rồi revoke đúng token đã chụp. Thêm regression thứ năm bảo đảm chat cũ không
  render hoặc mở khóa submission của phiên mới. Năm test hiện đạt.
- Khi logout, xóa danh sách chat/session/memory/project/timeline được render,
  reset các cờ tác vụ và bỏ qua nhánh async cũ. Giữ hành vi auth đã có của ứng dụng;
  không yêu cầu tài khoản hay mật khẩu của người dùng cho các lượt nghiệm thu.
- Giới hạn cả endpoint lịch sử cũ: `limit` 1–100 và `offset >= 0`. Trước đó
  SQLite `LIMIT -1` có thể bỏ giới hạn số dòng. Test xác minh HTTP 422 khi tham
  số sai, giữ nguyên kết quả cho tham số hợp lệ. Trang cursor vẫn giới hạn 100
  tin/lượt, tránh tải toàn bộ lịch sử; không tuyên bố tối ưu throughput nhiều user.
- Metadata memory IDs hỏng trong một tin cũ được xử lý tương thích với endpoint
  list cũ; không làm cả trang lịch sử thất bại hoặc nhầm thành lỗi cursor.
- CI Web được cập nhật chạy thêm `web-ui/auth.test.js`. Chỉ kiểm chứng local;
  chưa push, chưa có kết quả GitHub Actions cho bản sửa này.

Harness mới: `scripts/verify_web_auth.py`. Nó tạo account/DB tổng hợp, gửi login/
logout qua Gateway/FastAPI thật và dùng Chromium giữ lại response để kiểm tra
request đến muộn. Các kiểm tra auth/trí nhớ không đo chất lượng LLM.

## API lịch sử mới

`GET /v1/sessions/{session_id}/messages/page?limit=100&before=<message_id>`

- Yêu cầu Bearer token. Phiên không thuộc user trả 404.
- `limit` từ 1 đến 100; giá trị ngoài khoảng trả 422.
- Bỏ `before` để lấy trang mới nhất. Cursor sai/thuộc phiên khác trả 400.
- Response: `{ "messages": [...], "next_before": "..." }`.
- Tin trong mỗi trang theo thứ tự hội thoại; `next_before=null` khi đã hết.
- Client chèn trang cũ phía trước danh sách. Không thay đổi schema SQLite.
- Endpoint `/messages` cũ cũng giới hạn `limit` 1–100 và `offset >= 0`.

## Kiểm chứng sau sửa

Từ `/workspace/dusnx-platform`, các lệnh socket/Chromium cần quyền thực thi phù hợp
trong cloud sandbox. Dùng output-dir mới để giữ nguyên bằng chứng trước.

| Kiểm tra | Kết quả |
|---|---|
| `PYTHONPATH=python/src:python/apps:python:.:scripts DUSNX_DATA_DIR=/tmp/dusnx-improvement-full OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 python/.venv/bin/python -m pytest python/tests -q --tb=short` | **201 passed**, không skip |
| `node --test web-ui/app.test.js web-ui/auth.test.js powerpoint-addin/taskpane.test.js` | **25 passed** khi chạy đầy đủ với quyền spawn |
| `PATH=/workspace/.dusnx-tools/dotnet:$PATH OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 python/.venv/bin/python scripts/verify_chat_history.py --output-dir runtime/history-improvement-03` | **6/6 nhóm đạt**, Chromium/Gateway/FastAPI/SQLite thật |
| `PATH=/workspace/.dusnx-tools/dotnet:$PATH OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 python/.venv/bin/python scripts/verify_memory_reliability.py --output-dir runtime/core-improvement-01` | **10/10 nhóm đạt**, gồm backup/restore DB tổng hợp |
| Ruff cho hai file kiểm tra mới, Node syntax, `git diff --check` | Đạt; không tuyên bố lint toàn repo sạch |

Lượt kiểm chứng cuối sau hardening:

| Kiểm tra | Bằng chứng/kết quả |
|---|---|
| Python full suite | 201 passed; có kiểm tra giới hạn endpoint list và metadata hỏng |
| `scripts/verify_web_auth.py --output-dir runtime/auth-hardening-final` | 5/5 nhóm đạt, Chromium + auth HTTP thật |
| `scripts/verify_chat_history.py --output-dir runtime/history-hardening-final` | 6/6 nhóm đạt |
| `scripts/verify_memory_reliability.py --output-dir runtime/core-hardening-final` | 10/10 nhóm đạt |
| .NET Release build và Gateway tests | 0 warning/error, 7/7 đạt |
| Ruff cho `verify_web_auth.py`, `verify_chat_history.py`, `test_chat_history_pagination.py` | Đạt |
| `scripts/verify_chat_provenance.py --output runtime/cloud/provenance-hardening.json` | **Exit 1 / unverified**: memory/clarification đạt, generation trả `provider_error`, `provider_ok=false` |

Các lệnh harness dùng cùng PATH/OMP/MKL và working directory như bảng trên.
Lượt auth-hardening-01 thất bại vì harness đọc danh sách route giữ lại trước khi
callback hoàn tất `route.fetch()`. Đã chuyển fetch ra ngoài callback và chạy lại;
auth-hardening-02 cùng auth-hardening-final đạt, không nới assertion.

History harness kiểm tra 205 tin cùng timestamp, thứ tự/phân trang, đổi phiên khi
request đang chờ, lỗi trang rồi thử lại, nút được reset và đăng xuất khi request
chưa xong. API tests kiểm tra tin mới append giữa hai trang, cursor khác user/phiên,
phiên trống, giới hạn và endpoint tương thích cũ.

Evidence local (được ignore): `runtime/history-improvement-03/report.json`,
`runtime/history-improvement-03/history.png`, `runtime/core-improvement-01/report.json`.
Lượt history-01 thất bại do harness dùng string eval bị CSP từ chối; đã sửa chờ
bằng JavaScript function, giữ nguyên assertion. Lượt history-02 và history-03 đạt.
Chromium có sẵn tại `/usr/bin/chromium`; tải browser từ CDN Playwright bị policy
chặn, nên harness dùng executable có sẵn với TLS/CSP không bị nới lỏng.

## Còn thiếu và thứ tự tiếp theo

Kiểm tra bổ sung về nghi vấn Ollama chưa mở/cập nhật lỗi:
Ollama cloud trả HTTP 200 tại `/api/version` (0.40.13), `/api/tags` trả danh sách
model trống. FastAPI và Gateway trả HTTP 200; router được nạp. Registry trả 200,
nhưng kết nối domain lưu blob vẫn bị proxy trả 403. Chưa có bằng chứng bản cập
nhật Ollama hỏng; không thể suy ra trạng thái Windows từ các kết quả cloud này.
Đã bổ sung `error=model_missing` vào health khi Ollama chạy nhưng thiếu model,
và thông báo Web riêng cho thiếu model/không kết nối được dịch vụ. Kiểm tra cuối:
**205 Python tests**, **26 JavaScript tests** đạt. Đối chiếu Chromium với Ollama
thật ở `runtime/ollama-readiness-check-01/readiness.json`.

1. **Bắt buộc cho nghiệm thu chatbot thật:** tải `qwen2.5:0.5b`. Registry đã trả
   HTTP 200, nhưng domain lưu blob
   `dd20bb891979d25aebc8bec07b2b3bbc.r2.cloudflarestorage.com` vẫn bị proxy trả 403.
   Cả hai domain đã lưu trong draft; runtime vẫn chỉ báo `registry.ollama.ai`.
   UI xuất bản môi trường bị lỗi, chưa xác định nguyên nhân qua công cụ hiện có.
   Báo cáo sự cố đã được người dùng gửi, không có bằng chứng platform đã sửa.
   Ollama `/api/tags` hiện không có model, `provider_ok=false`. Không lặp yêu cầu
   người dùng bấm/lưu lại cấu hình khi chưa có trạng thái mới. Khi policy thực sự
   được áp dụng, tiếp tục bằng:

   ```bash
   OLLAMA_HOST=127.0.0.1:11434 /workspace/.dusnx-tools/ollama/bin/ollama pull qwen2.5:0.5b
   python/.venv/bin/python scripts/verify_chat_provenance.py --output runtime/cloud/provenance-new-run.json
   ```

   Nếu tải blob bị chặn ở domain tiếp theo, bổ sung đúng domain được báo qua
   cấu hình hỗ trợ. Không dùng mock hoặc bypass proxy để tuyên bố generation đạt.
2. **Chất lượng mô hình:** log training/config gốc sẽ giúp kiểm tra learning curve.
   Chỉ cân nhắc retrain sau khi có lỗi được đo và dữ liệu cải thiện. Data v2/human
   review/test độc lập vẫn cần xác minh theo `LLM_V2_GATE_NEXT.md`; không mở
   holdout v3 hoặc promote candidate trong đợt này.
3. **Tích hợp mở rộng:** PowerPoint Desktop cần nghiệm thu Office thật; mock không
   thay thế bước này. Word/Teams/Zalo/image không được tính là hoàn tất chỉ từ
   skeleton. Chúng không chặn phạm vi Web core đã chọn.
4. **Trước public production:** cần đánh giá concurrency (DB lock qua provider),
   retention/purge, proxy/rate-limit, CSP còn inline handlers và load test thực tế.
   Các phần này chưa được triển khai hoặc nghiệm thu trong đợt sửa lịch sử chat.

Đã cập nhật draft `install_script`/`start_skill` cho môi trường, checkpoint và
verification harness. Lưu draft không áp dụng network policy hoặc publish snapshot.
Sau khi gỡ chặn và kiểm chứng generation, người dùng có thể Publish môi trường
để giữ filesystem đã chuẩn bị; tiến trình dịch vụ phải khởi động lại ở task mới.

## Nghiệm thu thực tế và bàn giao trên máy Windows (02/11/2026)

Môi trường: Windows native (`D:\Projects\dusnx-platform`), Ollama 0.40.13 (`127.0.0.1:11434`),
.NET 8.0.427, Node v24.20.0, Python 3.12.10 trong `python/.venv`, Playwright Chromium 153.0.8010.12.
Cổng 8080 thuộc Docker Desktop (`com.docker.backend.exe`, PID 8520); nghiệm thu sử dụng cổng độc lập
(ví dụ Gateway 8088 / AI 8000) hoặc harness `Stack` tự cấp phát cổng trống.

### 1. Bảng yêu cầu → Bằng chứng → Kết quả

| Yêu cầu | Bằng chứng thực tế | Kết quả |
|---|---|---|
| **Web Demo luồng lõi**<br>Web → Gateway (ASP.NET Core) → FastAPI → Router đã train → Ollama sinh văn bản thật | - `scripts/verify_chat_provenance.py` chạy qua Gateway và Ollama thật.<br>- `scripts/verify_week4_web.py` dùng Chromium thao tác UI thật.<br>- Provenance: `response_source=llm`, `provider_called=true`, `provider_ok=true`, `model_used=qwen2.5:0.5b`, `routing_source=model`. | **ĐẠT** |
| **Bảo mật và Phân trang lịch sử**<br>Auth token expiry, late response discard, phân trang cursor >200 tin | - `scripts/verify_web_auth.py` (5/5 nhóm): 401 token clear, late response guard.<br>- `scripts/verify_chat_history.py` (6/6 nhóm): phân trang cursor tin nhắn, không lệch thứ tự, cô lập session. | **ĐẠT** |
| **Độ tin cậy của Trí nhớ (Memory)**<br>Active / supersede, loại trừ quyết định cũ, cô lập user | - `scripts/verify_memory_reliability.py` (10/10 nhóm).<br>- `scripts/verify_sqlite_backup_restore.py`: sau restore, memory truy xuất đúng bản cập nhật mới nhất (`MongoDB`), loại trừ bản cũ (`PostgreSQL`). | **ĐẠT** |
| **Đánh giá song ngữ VI / EN / Auto**<br>13 ca kiểm thử đa dạng, giữ nguyên văn bản trả về | - `scripts/verify_bilingual_generation.py`: 13/13 transport passed, 10/13 linguistic match, 3/13 divergent (do giới hạn mô hình sub-1B). Lưu nguyên văn tại `runtime/bilingual-generation/`. | **ĐẠT CÓ GHI NHẬN GIỚI HẠN** |
| **Đánh giá Router có căn cứ**<br>Phân biệt file hash, load kiến trúc, gọi inference, và độ chính xác dự đoán | - `scripts/verify_router_diagnostic.py`: SHA-256 khớp chuẩn, load đạt 100%.<br>- Đánh giá trên `benchmarks/benchmark_v2_ai_diagnostic.jsonl` (11 turns recurrent): Agent acc 63.6%, Intent acc 36.4%, Action acc 36.4%.<br>- Holdout v3 (`benchmarks/holdout_v3.jsonl`) được khóa bảo tồn. | **ĐẠT (RÕ RANH GIỚI)** |
| **Xác minh Backup / Restore SQLite**<br>ACID backup trên DB WAL, khôi phục và kiểm chứng tính toàn vẹn | - `scripts/verify_sqlite_backup_restore.py`:<br>  + Level 1: DB tổng hợp khôi phục, khởi động stack, auth/session/memory/retry receipt toàn vẹn.<br>  + Level 2: `backup-data-protected/` kiểm tra read-only, `journal_mode=wal`, `integrity_check=ok`. | **ĐẠT** |

### 2. Bảng lỗi → Tái hiện → Nguyên nhân đã chứng minh → Bản sửa → Regression

| Lỗi phát hiện | Cách tái hiện | Nguyên nhân đã chứng minh | Bản sửa | Regression test |
|---|---|---|---|---|
| **Lỗi 1: Windows Console CP1252 Crash** | Chạy script Python in chuỗi tiếng Việt trên Windows CMD/PowerShell mặc định. | `sys.stdout` mặc định dùng bảng mã Windows-1252, không mã hóa được ký tự Unicode tiếng Việt (như `\u1edb`). | Thêm cấu hình encoding an toàn: `if hasattr(sys.stdout, "reconfigure"): sys.stdout.reconfigure(encoding="utf-8")`. | Tất cả test script (`verify_bilingual_generation.py`, `verify_sqlite_backup_restore.py`, `verify_router_diagnostic.py`) chạy in tiếng Việt trơn tru. |
| **Lỗi 2: Xung đột cổng 8080 với Docker Desktop** | Khởi chạy harness gọi trực tiếp `http://127.0.0.1:8080`. | Docker Desktop (`com.docker.backend.exe`, PID 8520) chiếm giữ cổng 8080 từ trước cho dịch vụ Task Tracker. | Bổ sung class `Stack` tự động dò tìm cổng ngẫu nhiên khả dụng và hỗ trợ tham số `--gateway` linh hoạt. | `scripts/verify_week4_web.py` và `scripts/verify_week4_runtime.py` vượt qua 100% không xung đột cổng. |
| **Lỗi 3: Biến `args` chưa định nghĩa trong harness** | Gọi trực tiếp hàm kiểm thử sau khi tái cấu trúc module. | Biến CLI `args` được tham chiếu bên trong hàm con sau khi tách hàm. | Đổi thành tham số tường minh `gateway` và `data_dir` truyền vào hàm. | Tách biệt gọi hàm nội bộ và gọi qua CLI không phát sinh `NameError`. |
| **Lỗi 4: Xung đột thư mục `Stack` khi Restore** | Khởi tạo `Stack` trên thư mục đã có file database restore sẵn. | `Stack.__init__` gọi `mkdir(parents=True, exist_ok=False)` nên báo `FileExistsError`. | Khởi tạo instance `Stack(target_dir)` trước để tạo cây thư mục, sau đó copy database đã restore vào `stack.directory / "ai"` rồi mới kích hoạt context manager `with stack:`. | `scripts/verify_sqlite_backup_restore.py` khởi động và kiểm thử stack trên DB khôi phục thành công. |
| **Lỗi 5: Whitespace vi phạm `git diff --check`** | Chạy `git diff --check` trước khi commit. | Tồn tại dòng trống ở cuối file (trailing newlines) tại `scripts/verify_week4_runtime.py` và `docs/PROJECT_STATUS_20261102.md`. | Dọn dẹp ký tự thừa cuối file để `git diff --check` trả về exit code 0. | `git diff --check` trả về mã 0 sạch hoàn toàn. |

### 3. Đánh giá Song ngữ VI / EN / Auto (13 Ca kiểm thử)

Thực hiện qua `scripts/verify_bilingual_generation.py` với Gateway và Ollama `qwen2.5:0.5b` thật:
- **Tổng số ca:** 13 ca kiểm thử độc lập bao quát các tương tác.
- **Transport / Contract:** 13/13 ca đạt (`provider_called=true`, `provider_ok=true`, `response_source=llm`, câu trả lời không rỗng).
- **Độ tương thích ngôn ngữ nội dung:** 10/13 ca khớp chính xác với ngôn ngữ mong đợi; 3/13 ca xuất hiện bất đồng ngôn ngữ (divergence).
- **Phân tích ca bất đồng ngôn ngữ (Cross-lingual divergence):**
  1. `CASE_03_VI_PREF_EN`: Câu hỏi tiếng Việt (`"Giải thích ngắn gọn khái niệm máy học là gì."`) nhưng người dùng cài đặt `preferred_language=en`. Mô hình 0.5B trả lời bằng tiếng Việt thay vì dịch/trả lời bằng tiếng Anh.
  2. `CASE_04_EN_PREF_VI`: Câu hỏi tiếng Anh (`"What are two key benefits of automated unit testing?"`) nhưng người dùng cài đặt `preferred_language=vi`. Mô hình trả lời bằng tiếng Anh thay vì dịch/trả lời bằng tiếng Việt.
  3. `CASE_07_AUTO_SHORT_CONTEXT`: Lệnh ngắn phụ thuộc lịch sử ngữ cảnh.
- **Nguyên nhân kỹ thuật đã xác minh:**
  Mô hình `qwen2.5:0.5b` (dung lượng tham số ~490M) chịu ảnh hưởng mạnh bởi ngôn ngữ của câu hỏi đầu vào (prior tokens) lấn át chỉ thị ngôn ngữ trong system prompt khi có xung đột chéo giữa ngôn ngữ hỏi và ngôn ngữ đích. Khi ngôn ngữ câu hỏi và preferred_language đồng nhất (VI+VI hoặc EN+EN), mô hình tuân thủ ngôn ngữ rất tốt.
- **Tính minh bạch:**
  Toàn bộ câu trả lời nguyên văn được lưu giữ tại `runtime/bilingual-generation/report.json` và bảng duyệt `runtime/bilingual-generation/review_table.md`. Các ô đánh giá con người được để trống (`[ ] needs_human_review`) để chờ người thật duyệt; không tự gán nhãn AI đánh giá là human review.

### 4. Đánh giá Router có căn cứ và Ranh giới

- **Tính toàn vẹn Checkpoint:**
  - File: `training-results/colab-run-01/extracted/dusnx-router-full-01/router.pt`
  - SHA-256: `56f56e6d61afc264fb02d690d2872fb3ac5db9749a659c8493fd9d99eab7e7b1` (Khớp 100%).
  - Kiến trúc: 16,384 vocab, 6 intents, 3 agents, 6 next actions. Trọng số load strict đạt chuẩn.
- **Inference thực tế:**
  - Provenance trả `routing_source=model` chứng minh mạng nơ-ron hồi quy PyTorch đã tính toán phân phối xác suất logits.
- **Độ chính xác trên tập Diagnostic được phép (`benchmarks/benchmark_v2_ai_diagnostic.jsonl`, 11 turns sequence):**
  - **Agent Accuracy:** **63.64%** (Macro-F1: 0.5079) - Mô hình nhận diện đúng agent phần lớn các trường hợp (conversation, productivity, search_rag).
  - **Intent Accuracy:** **36.36%** (Macro-F1: 0.3278) - Nhầm lẫn giữa `research` và `chat`, hoặc `recommendation` và `followup`.
  - **Next Action Accuracy:** **36.36%** (Macro-F1: 0.3278) - Nhầm lẫn giữa `reply` và `search`.
  - **Cả 3 Heads khớp hoàn toàn:** **27.27%** (3/11 turns).
- **Quy tắc nghiệp vụ (Business-Rule Overrides):**
  Trong ứng dụng thực tế, các quy tắc nghiệp vụ (`preference_instruction`, `_detect_missing_context_query`, `_detect_remember_intent`, `pending_decision` confirmation) được thiết kế ưu tiên cao hơn đầu ra của router nhằm bảo đảm ứng dụng không hành động sai khi router nơ-ron phân loại nhầm.
- **Bảo tồn Holdout v3:**
  Tập dữ liệu `benchmarks/holdout_v3.jsonl` được **KHÓA BẢO TỒN**, tuyệt đối không mở, không chạy và không dùng để điều chỉnh mô hình.

### 5. Xác minh Khôi phục Backup SQLite (2 Cấp độ)

- **Cấp độ 1: Dữ liệu tổng hợp (End-to-End Synthetic Restore & Idempotency):**
  - Khởi tạo stack với database SQLite ở chế độ WAL.
  - Tạo tài khoản, phiên làm việc, gửi hội thoại dài (>200 tin), thiết lập memory với 2 quyết định (bản ghi đầu `PostgreSQL`, bản ghi sau ghi đè thành `MongoDB`).
  - Thực hiện sao lưu thông qua SQLite Backup API (`src.backup(dst)`), đảm bảo tính toàn vẹn ACID ngay cả khi database đang mở.
  - Khôi phục sang thư mục độc lập mới và kiểm tra `PRAGMA integrity_check` trả về `"ok"`.
  - Khởi động stack trên bản sao lưu đã khôi phục:
    + Đăng nhập tài khoản thành công.
    + Lịch sử tin nhắn được đọc đầy đủ và chính xác thứ tự.
    + Trí nhớ hoạt động chuẩn: Quyết định mới `MongoDB` được trả về, quyết định cũ `PostgreSQL` bị loại trừ chính xác.
    + Gửi lại request cũ: Hệ thống nhận diện receipt có sẵn, trả về kết quả replay mà không nhân đôi bản ghi mutation.
- **Cấp độ 2: Dữ liệu cá nhân được bảo vệ (`backup-data-protected/`):**
  - Thực hiện kiểm tra an toàn ở chế độ chỉ đọc (read-only).
  - Xác nhận `journal_mode=wal` và `PRAGMA integrity_check` = `"ok"`.
  - Thống kê an toàn không làm lộ dữ liệu:
    + `auth.db`: 2 users, 2 sessions.
    + `memory.db`: 36 messages, 2 memories.
  - Không dump nội dung hoặc token cá nhân ra log/evidence công khai.

### 6. Thống kê Kiểm thử Tách bạch theo đúng Phạm vi

Tránh gộp các bộ test khác nhau để tránh ngộ nhận:

| Phân hệ kiểm thử | Số lượng test | Trạng thái | Ghi chú phạm vi |
|---|---|---|---|
| **Python Unit & Integration** (`pytest`) | **205 passed** | Thành công (105s) | Toàn bộ kiểm thử logic lõi, state, auth, pagination, memory, routing, provider |
| **Web UI Core Tests** (`node --test`) | **13 passed** | Thành công | Kiểm thử render, XSS protection, giao diện chat |
| **Web Auth Guard Tests** (`node --test`) | **5 passed** | Thành công | Token expiry, logout state cleanup, late response discarding |
| **PowerPoint Add-in Mock** (`node --test`) | **8 passed** | Thành công | Unit test kiểm thử taskpane logic với in-memory mock của Office JS API.<br>*(Làm rõ: Mock KHÔNG chứng minh chạy được trên PowerPoint Desktop Office 365)* |
| **Tổng số JavaScript Tests** | **26 passed** | Thành công (216ms) | Bao gồm 13 Web UI + 5 Web Auth + 8 PowerPoint Mock |
| **.NET Gateway Tests** | **7 passed** | Thành công | Pagination endpoint, concurrent stream append, identity forwarding |
| **PowerShell Health Tests** | **6 passed** | Thành công | Khế ước `/health` và `/v1/health` của Gateway và AI API |
| **Harness Web Auth** (`verify_web_auth.py`) | **5/5 groups** | Thành công | Real Chromium + Gateway + late response discard |
| **Harness Chat History** (`verify_chat_history.py`) | **6/6 groups** | Thành công | >200 messages pagination, cursor ordering, session isolation |
| **Harness Memory Reliability** (`verify_memory_reliability.py`) | **10/10 groups** | Thành công | Atomic supersede, isolation, corrupt DB refusal |
| **Harness Chat Provenance** (`verify_chat_provenance.py`) | **1 test** | Thành công | Real Ollama qwen2.5:0.5b generation + trained router |
| **Harness Week 4 Web** (`verify_week4_web.py`) | **8/8 tests** | Thành công | Confirmation buttons, XSS safety, mobile 390px, 401 token clear |
| **Harness Week 4 Runtime** (`verify_week4_runtime.py`) | **19/19 tests** | Thành công | RT-01 đến RT-16, restoration, SHA256 integrity |
| **Harness Bilingual Generation** (`verify_bilingual_generation.py`) | **13 tests** | 13/13 transport ok, 10/13 lang match | Kiểm thử song ngữ 13 ca trên mô hình thật |
| **Harness SQLite Backup/Restore** (`verify_sqlite_backup_restore.py`) | **2 levels** | Thành công | Level 1 synthetic restore & idempotency + Level 2 protected check |
| **Harness Router Diagnostic** (`verify_router_diagnostic.py`) | **11 turns** | Hoàn thành | Đánh giá 11 turns trên `benchmark_v2_ai_diagnostic.jsonl` |

### 7. Ranh giới Bàn giao và Các phần chưa hoàn tất

- **Đã bàn giao và kiểm chứng:**
  - Demo Web core: Web → Gateway (ASP.NET Core) → FastAPI → Trained router (`router.pt`) → Ollama (`qwen2.5:0.5b`) sinh câu trả lời thật.
  - Quản lý phiên, lịch sử chat dài (>200 tin) với phân trang cursor mượt mà.
  - Quản lý trí nhớ dài hạn (ghi nhớ, ghi đè quyết định, loại trừ quyết định cũ).
  - Cơ chế idempotent retry và khôi phục SQLite backup an toàn.
- **Ranh giới và Phần chưa hoàn tất:**
  1. **Khả năng dịch chéo ngôn ngữ của mô hình nhỏ:** `qwen2.5:0.5b` chưa đáp ứng dịch chéo mượt mà khi hỏi bằng tiếng Việt nhưng yêu cầu trả lời tiếng Anh (hoặc ngược lại).
  2. **Độ chính xác router nơ-ron thuần túy:** Đạt 63.6% Agent và 36.4% Intent/Action trên tập diagnostic; hệ thống đang dựa vào các business rules để bảo vệ độ chính xác nghiệp vụ.
  3. **PowerPoint Desktop:** Mới kiểm chứng mock in-memory trong Node; chưa nghiệm thu sideload thực tế trên Office 365 Desktop.
  4. **Môi trường Production diện rộng:** Chưa thực hiện load test hàng ngàn người dùng đồng thời, chưa thiết lập SSL termination và reverse proxy production.
