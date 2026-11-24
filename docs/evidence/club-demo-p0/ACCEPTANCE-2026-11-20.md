# Club IT Assistant — P0 Acceptance (2026-11-20)

Branch: `fix/club-demo-p0`
Runtime: club stack `:8010` / `:8090`; production `:8000` / `:8080` untouched.

## Runtime identity (read from `/health`)

| Item | Value |
|---|---|
| AI API | `status=ok`, `provider=ollama` |
| Model | `configured_model=dusnx-vi-club`, `model_available=true` |
| `rag.py` sha256 | `b31b1dd971ebb3031639cc28adc821c3922462cc662712710a25b020c980f3da` |
| `main.py` sha256 | `3d91e69f75fe9f3f3446542f461b644b9c2ee8961afbee0b3c94604e2f05651a` |
| `provider.py` sha256 | `7c8c74224e8b95d49389252f024bbdb48e39bfa95e859ccca475d567f7d1bce8` |
| RAG index | `runtime/club-rag/rag.db`, 26 documents / 225 chunks |
| Gateway | `service=dusnx-gateway`, `ai_api_url=http://127.0.0.1:8010`, binary `be18e369…` |

## Offline gates

| Suite | Result |
|---|---|
| `pytest -q` (python/) | **501 passed**, 0 skipped (Colab checkpoint đã giải nén), 0 failed |
| `node --test web-ui/*.test.js` | **24 / 24 passed** (269 ms) |
| Club harness, 28 cases (`cases_sha256 45778b9…`) | answer 20: hit@1/3/5 **1.0**, scoped gate **1.0**, grounded-or-abstained **1.0**, citation **1.0**; refuse 8: **1.0** |
| Repo-index harness, 16 cases (repo `rag.db`) | hit@1 **1.0**, hit@k **1.0**, MRR **1.0**, gate **1.0**, citation OK, 13 extractive answers, 4/4 negatives rejected |

Hai chỉ mục được đo riêng; không được trích số liệu CLB cho chỉ mục repo hoặc ngược lại. Lệnh đo repo phải chỉ định rõ DB vì mặc định hiện ưu tiên chỉ mục CLB nếu có:

```bash
DUSNX_RAG_DB=python/data/rag.db python scripts/eval_rag.py --json runtime/rag-eval.json   # repo
DUSNX_RAG_DB=runtime/club-rag/rag.db python python/scripts/evaluate_domain_rag.py \
  --db runtime/club-rag/rag.db --cases datasets/club_corpus_v1/test_set.jsonl            # CLB
```

## Live acceptance — 3 consecutive runs on `:8090`

| Run | Timestamp (UTC) | Cases | Trained Model (LoRA) | API comparison | Gemini Tokens | API latency | Primary answer |
|---|---|---|---|---|---|---|---|
| 1 | 2026-11-20T17:58:46Z | **13 / 13** | `dusnx-vi-club` (`ollama` / `llm`, 531 ms) | `gemini-3.1-flash-lite` | 28 | 1,063 ms | `local/rag` & `ollama` |
| 2 | 2026-11-20T17:58:48Z | **13 / 13** | `dusnx-vi-club` (`ollama` / `llm`, 359 ms) | `gemini-3.1-flash-lite` | 28 | 984 ms | `local/rag` & `ollama` |
| 3 | 2026-11-20T17:58:50Z | **13 / 13** | `dusnx-vi-club` (`ollama` / `llm`, 344 ms) | `gemini-3.1-flash-lite` | 28 | 953 ms | `local/rag` & `ollama` |

- Logs: `docs/evidence/club-demo-p0/run_1.log` … `run_3.log`.
- Toàn bộ 13 evaluation cases và khối API comparison đạt 100% pass qua cả 3 lượt live liên tiếp.
- Minh chứng năng lực kết hợp Hybrid: RAG trích dẫn tất định cho câu hỏi quy chế (`[S1]`), mô hình tự huấn luyện (`dusnx-vi-club` qua Ollama) sinh lời phản hồi hội thoại thật (CASE-13: `provider_called: true`, `source_type: "llm"`, `model_used: "dusnx-vi-club"`, phản hồi *"Rất vui được giúp bạn! Chúc bạn có ngày tốt lành nhé!"* giống nhau ở cả 3 lượt do giải mã greedy), và thẻ so sánh gọi trực tiếp Google Gemini 3.1 Flash-Lite thật.
- Độ trễ API bên ngoài dao động theo mạng và hạn mức (đã quan sát 0,9 s đến 55,3 s giữa các lần đo). Con số trong bảng là giá trị thật của từng lượt, không phải trung bình.
- Nhãn thời gian trong toàn bộ log ghi chuẩn UTC (`gmtime`).
- Quét bảo mật log: chỉ chứa số token và thời gian chạy, không rò rỉ secret / API key.

## Resolved & Verified Fixes

1. **Đồng bộ triệt để Seed Data Bảng tin & DB (Khắc phục rơi mục 3 -> 1):**
   - Đã cập nhật `ensure_default_channels` trong `club_chat.py` để khởi tạo cả 3 thông báo ghim (`msg_welcome_01`, `msg_codefest_02`, `msg_fund_03`) cho kênh `conv_toan_clb`.
   - Đã migrate dữ liệu vào SQLite `runtime/club-data/club_chat.db` với đầy đủ quyền và tác giả chuẩn.
   - Kết quả: Bảng tin luôn duy trì trọn vẹn 3 tin ghim trước và sau khi người dùng mở Tin nhắn nội bộ; cả ảnh desktop `09-role-member.png` và mobile `11-pwa-mobile.png` đều hiển thị đồng nhất 3 thông báo chuẩn corpus.
2. **Minh chứng Mô hình Tự huấn luyện (LoRA / `dusnx-vi-club`) — trả lời thật, không kịch bản:**
   - Bổ sung `CASE-13` vào bộ kiểm thử live: gửi câu hỏi hội thoại tương tác ("Cảm ơn bạn rất nhiều!"), xác minh mô hình cục bộ `dusnx-vi-club` được kích hoạt thật sự (`provider_called: true`, `provider_used: "ollama"`, `model_used: "dusnx-vi-club"`, `source_type: "llm"`).
   - Chào/cảm ơn thuần túy được gửi tới model với system prompt tối giản (không còn tiền tố "Hãy trả lời bằng tiếng Việt…" để model sao chép) và giải mã greedy (`temperature=0`, `top_k=1`, `num_predict=48`) — 0.5B ổn định hơn hẳn so với sampling và cho cùng một câu trả lời qua cả 3 lượt.
   - `sanitize_generated_reply` loại bỏ cả prompt leak ("Hãy trả lời...", "Câu hỏi của bạn là...", "Yêu cầu người dùng...") lẫn narration của vòng retry huấn luyện ("Câu trả lời lần 1 đã không đạt kiểm tra…", "Xin hãy viết lại từ đầu…"). Với lượt small-talk, cơ chế retry/translation tự động được bỏ qua vì nó chính là nguồn sinh ra câu lặp.
   - Nếu model vẫn trả về chuỗi không dùng được (lẫn CJK, rỗng, hoặc narration), hệ thống phục vụ một câu tiếng Việt cố định nhưng ghi trung thực `response_source: "template"` và `model_used: null` — không gán câu template cho model. Đường dự phòng này có regression test riêng; 3 lượt nghiệm thu không phải dùng tới nó.
   - Lượt chào/cảm ơn được trả lời một lần, không stream token preview xuống UI, để văn bản cuối đã kiểm định là nội dung duy nhất người dùng thấy (SSE chỉ phát event `done`); đã kiểm tra trực tiếp `/v1/chat/stream`.
   - Cập nhật script `verify_club_demo_p0.py` kiểm tra cấm các từ khóa rò rỉ prompt, assert `source_type == "llm"`, và ghi nhận trường `model_used` vào từng bản ghi case.
3. **Thu hẹp Regex `_CAPABILITY_QUESTION` tránh chặn nhầm câu hỏi RAG:**
   - Neo chặt regex nhận diện câu hỏi năng lực, bổ sung nhánh `"bạn biết gì"` / `"chức năng của bạn"` nhưng chỉ khi câu hỏi kết thúc ngay (`"Bạn biết gì?"`), không khớp `"Bạn biết gì về CLB IT?"`.
   - Đảm bảo các câu hỏi tra cứu nội dung CLB (như "Bạn có biết chủ nhiệm CLB là ai không?", "Bạn biết gì về CLB IT?", "Trưởng ban truyền thông là người nào?") không bị chuyển hướng sai sang thẻ giới thiệu chức năng mà đi vào luồng RAG chính xác.
4. **Chuẩn hóa Metadata người gửi tin nhắn (`club_list_messages`):**
   - Bổ sung hàm `get_user_by_username` vào `AuthDB` (`auth.py`).
   - Cập nhật endpoint `/v1/club/conversations/{conv_id}/messages` trong `main.py` tra cứu người gửi qua cả `user_id` và `username`, đồng thời ánh xạ vai trò và tên hiển thị đầy đủ ("Nguyễn Minh Anh (Chủ nhiệm CLB)", "Đỗ Nam Khánh (Trưởng ban kỹ thuật)", "Lê Quốc Bảo (Phó chủ nhiệm)").
   - Kết quả: Ảnh `10-messaging.png` hiển thị đúng danh tính và badge chức vụ của từng người gửi, không còn bị hiển thị username thô hay role member mặc định.
5. **Chuẩn hóa Metadata & Nhãn Thời gian UTC:**
   - Số liệu pytest hiện tại: **500 passed, 0 failed, 0 skipped** (checkpoint Colab đã giải nén trong máy). Khi thiếu checkpoint, một số test Colab sẽ skip và tổng số passed giảm tương ứng.
   - Sửa script `verify_club_demo_p0.py` dùng `time.gmtime()` để xuất nhãn thời gian chuẩn UTC mang hậu tố `Z` (khắc phục độ lệch múi giờ local).
6. **`08-approval-pending.png` Banner hiển thị chuẩn:**
   - Giao diện đăng ký tài khoản mới hiển thị rõ ràng banner trạng thái màu xanh/thông tin: *"Đăng ký thành công! Tài khoản đang chờ Ban chủ nhiệm duyệt trước khi sử dụng."*
7. **`07-compare-api.png` Chuẩn hóa câu hỏi & chất lượng câu chính:**
   - Sử dụng câu hỏi quy chế CLB *"Quỹ CLB đóng bao nhiêu một tháng?"*. Model local trích dẫn chuẩn doc 16 `[S1]`, không lặp prompt `"Người dùng:"`. Thẻ so sánh Gemini Flash-Lite hiển thị token thật và độ trễ thật.
8. **`04-chat-codefest.png` Cô lập sự kiện CodeFest:**
   - Sử dụng `event_markers` trong `rag.py` ngăn trích xuất nhầm địa điểm từ Demo Day (doc 14). Trích dẫn độc quyền *"Địa điểm: sảnh tòa B. [S1]"*. Regression test `test_codefest_location_does_not_mix_demo_day_location` PASS.
9. **`11-pwa-mobile.png` Thanh điều hướng 6 tab & Chống tràn header:**
   - Bổ sung thanh điều hướng đáy `.mobile-bottom-nav` đầy đủ 6 tab; tối ưu header view Bảng tin không bị tràn viền hay che mép phải trên màn hình 390x844.
10. **Câu hỏi tổng quan CLB trả lời từ quy chế, không bám nhầm mẫu đơn:**
   - Trước đây "CLB IT là gì?" trích nhầm mẫu đơn đăng ký. Đã thêm route nhận diện câu hỏi tổng quan (`_CLUB_OVERVIEW_QUERY`) và hàm `_club_overview_answer` đọc trực tiếp các chunk của `01-quy-che-hoat-dong.md`, trả về mục đích, tôn chỉ và 3 ban chuyên môn kèm `[S1]`.
   - Route chỉ kích hoạt khi câu hỏi mở đầu bằng dạng "CLB IT là gì / giới thiệu về CLB / cho biết về CLB"; câu hỏi tài liệu cụ thể (ví dụ "Quy định sử dụng phòng lab…") vẫn đi luồng trích xuất thường. Regression test `test_overview_route_does_not_hijack_document_questions` PASS.
   - Đã kiểm tra live: "CLB IT là gì?" và "Bạn biết gì về CLB IT?" trả cùng nội dung quy chế có trích dẫn; "Quy định sử dụng phòng lab của CLB là gì?" vẫn trả đúng C1-C5.

## Giới hạn đã biết (ghi trung thực)

- Model `dusnx-vi-club` là LoRA trên nền Qwen2.5-0.5B; chất lượng hội thoại mở còn hạn chế. Chào/cảm ơn được xử lý ổn định bằng prompt tối giản + greedy, nhưng model chưa phù hợp cho câu trả lời dài, suy luận nhiều bước.
- Nếu model trả lời small-talk không dùng được, API trả một câu template và báo `response_source: "template"` (không giả gán cho model). Đây là đường dự phòng, không phải đường chính của 3 lượt nghiệm thu.
- Độ trễ Gemini API phụ thuộc mạng/hạn mức, đã dao động 0,9–55,3 s; thẻ so sánh hiển thị số đo thật từng lần.
- Ba nhóm ảnh UI được chụp trên build trước lượt sửa chat-copy này (`baf29a6`); các màn hình đó không đổi vì câu trả lời quy chế vẫn do `rag_extract` tất định sinh ra. Riêng CASE-13 không xuất hiện trong bộ ảnh.

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
