# Club IT Assistant — P0 Acceptance (2026-11-20)

Branch: `fix/club-demo-p0`
Runtime: club stack `:8010` / `:8090`; production `:8000` / `:8080` untouched.

## Runtime identity (read from `/health`)

| Item | Value |
|---|---|
| AI API | `status=ok`, `provider=ollama` |
| Model | `configured_model=dusnx-vi-club`, `model_available=true` |
| `rag.py` sha256 | `50185b3f55ceba8c5e1ccf5def47aca074ac26f290584485d9110033cefeb3d9` |
| `main.py` sha256 | `98cf3c42fba5395b2b9361454d08e57a8f63baddec3a9dc1095499a7f5e03573` |
| RAG index | `runtime/club-rag/rag.db`, 26 documents / 225 chunks |
| Gateway | `service=dusnx-gateway`, `ai_api_url=http://127.0.0.1:8010`, binary `5c78f521…` |

## Offline gates

| Suite | Result |
|---|---|
| `pytest -q` (python/) | **490 passed** (hoặc 489 passed, 1 skipped khi thiếu Colab checkpoint), 0 failed |
| `node --test web-ui/*.test.js` | **24 / 24 passed** (425 ms) |
| Club harness, 28 cases (`cases_sha256 45778b9…`) | answer 20: hit@1/3/5 **1.0**, scoped gate **1.0**, grounded-or-abstained **1.0**, citation **1.0**; refuse 8: **1.0** |
| Repo-index harness, 16 cases (repo `rag.db`) | hit@1 **1.0**, hit@k **1.0**, MRR **1.0**, gate **1.0**, citation OK, 13 extractive answers, 4/4 negatives rejected |

The two indices are measured separately; club metrics must not be quoted for the repo index, or vice versa.

## Live acceptance — 3 consecutive runs on `:8090`

| Run | Timestamp (UTC) | Cases | Trained Model (LoRA) | API comparison | Gemini Tokens | API latency | Primary answer |
|---|---|---|---|---|---|---|---|
| 1 | 2026-11-20T15:49:38Z | **13 / 13** | `dusnx-vi-club` (`ollama` / `llm`, 766 ms) | `gemini-3.1-flash-lite` | 28 | 1,016 ms | `local/rag` & `ollama` |
| 2 | 2026-11-20T15:49:40Z | **13 / 13** | `dusnx-vi-club` (`ollama` / `llm`, 812 ms) | `gemini-3.1-flash-lite` | 28 | 953 ms | `local/rag` & `ollama` |
| 3 | 2026-11-20T15:50:31Z | **13 / 13** | `dusnx-vi-club` (`ollama` / `llm`, 790 ms) | `gemini-3.1-flash-lite` | 28 | 50,297 ms | `local/rag` & `ollama` |

- Logs: `docs/evidence/club-demo-p0/run_1.log` … `run_3.log`.
- Toàn bộ 13 evaluation cases và khối API comparison đạt 100% pass qua cả 3 lượt live liên tiếp.
- Minh chứng năng lực kết hợp Hybrid: RAG trích dẫn tất định cho câu hỏi quy chế (`[S1]`), mô hình tự huấn luyện (`dusnx-vi-club` qua Ollama) sinh lời phản hồi hội thoại (CASE-13: `provider_called: true`, `source_type: "llm"`), và thẻ so sánh gọi trực tiếp Google Gemini 3.1 Flash-Lite thật.
- Nhãn thời gian trong toàn bộ log ghi chuẩn UTC (`gmtime`).
- Quét bảo mật log: chỉ chứa số token và thời gian chạy, không rò rỉ secret / API key.

## Resolved & Verified Fixes

1. **Đồng bộ triệt để Seed Data Bảng tin & DB (Khắc phục rơi mục 3 -> 1):**
   - Đã cập nhật `ensure_default_channels` trong `club_chat.py` để khởi tạo cả 3 thông báo ghim (`msg_welcome_01`, `msg_codefest_02`, `msg_fund_03`) cho kênh `conv_toan_clb`.
   - Đã migrate dữ liệu vào SQLite `runtime/club-data/club_chat.db` với đầy đủ quyền và tác giả chuẩn.
   - Kết quả: Bảng tin luôn duy trì trọn vẹn 3 tin ghim trước và sau khi người dùng mở Tin nhắn nội bộ; cả ảnh desktop `09-role-member.png` và mobile `11-pwa-mobile.png` đều hiển thị đồng nhất 3 thông báo chuẩn corpus.
2. **Minh chứng Mô hình Tự huấn luyện (LoRA / `dusnx-vi-club`):**
   - Bổ sung `CASE-13` vào bộ kiểm thử live: gửi câu hỏi hội thoại tương tác ("Cảm ơn bạn rất nhiều!"), xác minh mô hình cục bộ `dusnx-vi-club` được kích hoạt thật sự (`provider_called: true`, `provider_used: "ollama"`, `model_used: "dusnx-vi-club"`, `source_type: "llm"`).
   - Tối ưu `_CAPABILITY_QUESTION` trong `main.py` hỗ trợ xử lý mẫu câu hỏi định danh ("Bạn là ai?"), đảm bảo trợ lý phản hồi năng lực chuẩn xác.
3. **Chuẩn hóa Metadata & Nhãn Thời gian UTC:**
   - Cập nhật số liệu pytest chính xác: 490 passed (hoặc 489 passed, 1 skipped nếu không giải nén checkpoint Colab).
   - Sửa script `verify_club_demo_p0.py` dùng `time.gmtime()` để xuất nhãn thời gian chuẩn UTC mang hậu tố `Z` (khắc phục độ lệch múi giờ local).
4. **`08-approval-pending.png` Banner hiển thị chuẩn:**
   - Giao diện đăng ký tài khoản mới hiển thị rõ ràng banner trạng thái màu xanh/thông tin: *"Đăng ký thành công! Tài khoản đang chờ Ban chủ nhiệm duyệt trước khi sử dụng."*
5. **`07-compare-api.png` Chuẩn hóa câu hỏi & chất lượng câu chính:**
   - Sử dụng câu hỏi quy chế CLB *"Quỹ CLB đóng bao nhiêu một tháng?"*. Model local trích dẫn chuẩn doc 16 `[S1]`, không lặp prompt `"Người dùng:"`. Thẻ so sánh Gemini Flash-Lite hiển thị token thật và độ trễ thật.
6. **`04-chat-codefest.png` Cô lập sự kiện CodeFest:**
   - Sử dụng `event_markers` trong `rag.py` ngăn trích xuất nhầm địa điểm từ Demo Day (doc 14). Trích dẫn độc quyền *"Địa điểm: sảnh tòa B. [S1]"*. Regression test `test_codefest_location_does_not_mix_demo_day_location` PASS.
7. **`11-pwa-mobile.png` Thanh điều hướng 6 tab & Chống tràn header:**
   - Bổ sung thanh điều hướng đáy `.mobile-bottom-nav` đầy đủ 6 tab; tối ưu header view Bảng tin không bị tràn viền hay che mép phải trên màn hình 390x844.

## Danh mục 11 Ảnh Minh chứng UI Thực tế

Tất cả ảnh được lưu trữ tại `docs/evidence/club-demo-p0/screenshots/`:
1. `01-login.png`: Màn hình đăng nhập 4 role quick buttons (1280x850)
2. `02-chat-schedule.png`: Lịch & địa điểm sinh hoạt (Thứ 5 hằng tuần, 18:30-21:00, phòng A2-304, doc 03 `[S1]`)
3. `03-chat-fund.png`: Hạn đóng quỹ (50.000đ/tháng trước ngày 10, Phạm Thuỳ Dương, doc 16 `[S1]`)
4. `04-chat-codefest.png`: Địa điểm IT CodeFest 2026 (sảnh tòa B, doc 04 `[S1]`, cấm hội trường tòa C)
5. `05-chat-criteria.png`: Tiêu chí thành viên xuất sắc (40%/40%/20%, doc 18 `[S1]`)
6. `06-refusal-weather.png`: Câu hỏi thời tiết bị từ chối ngoài phạm vi, không bịa nguồn
7. `07-compare-api.png`: So sánh với Gemini API (gemini-3.1-flash-lite, 28 tokens thật, local chuẩn RAG)
8. `08-approval-pending.png`: Đăng ký tài khoản mới hiển thị banner trạng thái chờ duyệt
9. `09-role-member.png`: Bảng tin vai trò Thành viên (nút đăng thông báo bị ẩn, hiển thị đầy đủ 3 tin ghim đồng bộ DB)
10. `10-messaging.png`: Tin nhắn nội bộ & tin nhắn ghim chào mừng đồng bộ chuẩn corpus
11. `11-pwa-mobile.png`: Giao diện PWA mobile 390x844 responsive, hiển thị trọn vẹn 3 tin ghim và thanh bottom navigation 6 tab dưới đáy.
