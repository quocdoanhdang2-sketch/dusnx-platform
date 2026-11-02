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
