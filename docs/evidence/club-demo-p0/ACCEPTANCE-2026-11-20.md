# Club IT Assistant — P0 Acceptance (2026-11-20)

Branch: `fix/club-demo-p0`
Runtime: club stack `:8010` / `:8090`; production `:8000` / `:8080` untouched.

## Runtime identity (read from `/health`)

| Item | Value |
|---|---|
| AI API | `status=ok`, `provider=ollama` |
| Model | `configured_model=dusnx-vi-club`, `model_available=true` |
| `rag.py` sha256 | `50185b3f55ceba8c5e1ccf5def47aca074ac26f290584485d9110033cefeb3d9` |
| `main.py` sha256 | `d784c24061eaba31c5d6bee5b3d21452f720c2991776440634af074f9f30f0cc` |
| RAG index | `runtime/club-rag/rag.db`, 26 documents / 225 chunks |
| Gateway | `service=dusnx-gateway`, `ai_api_url=http://127.0.0.1:8010`, binary `d4cef91d…` |

## Offline gates

| Suite | Result |
|---|---|
| `pytest -q` (python/) | **490 passed, 1 skipped** (79.27 s) |
| `node --test web-ui/*.test.js` | **24 / 24 passed** (100.5 ms) |
| Club harness, 28 cases (`cases_sha256 45778b9…`) | answer 20: hit@1/3/5 **1.0**, scoped gate **1.0**, grounded-or-abstained **1.0**, citation **1.0**; refuse 8: **1.0** |
| Repo-index harness, 16 cases (repo `rag.db`) | hit@1 **1.0**, hit@k **1.0**, MRR **1.0**, gate **1.0**, citation OK, 13 extractive answers, 4/4 negatives rejected |

The two indices are measured separately; club metrics must not be quoted for the repo index, or vice versa.

## Live acceptance — 3 consecutive runs on `:8090`

| Run | Timestamp (UTC) | Cases | API provider / model | Tokens | API latency | Primary answer |
|---|---|---|---|---|---|---|
| 1 | 2026-11-20T15:03:36Z | **12 / 12** | `openai` / `gemini-3.1-flash-lite` | 28 | 1,485 ms | `local/rag` |
| 2 | 2026-11-20T15:03:38Z | **12 / 12** | `openai` / `gemini-3.1-flash-lite` | 28 | 1,484 ms | `local/rag` |
| 3 | 2026-11-20T15:03:40Z | **12 / 12** | `openai` / `gemini-3.1-flash-lite` | 28 | 1,500 ms | `local/rag` |

- Logs: `docs/evidence/club-demo-p0/run_1.log` … `run_3.log`.
- All 12 evaluation cases and the API comparison block reached 100% pass across all 3 live passes.
- Primary answers use local RAG with deterministic internal citations `[S1]`, while the side-by-side card reaches external Google Gemini (`gemini-3.1-flash-lite`) reporting real tokens and latency.
- Secret scan of the logs found only token counts, no credentials.

## Resolved & Verified Fixes (Full 6 Audit Discrepancies)

1. **`08-approval-pending.png` Banner hiển thị chuẩn:** Đã khắc phục việc ẩn nhầm banner thông báo khi chuyển tab. Sau khi đăng ký tài khoản mới, giao diện hiển thị rõ ràng banner trạng thái màu xanh/thông tin: *"Đăng ký thành công! Tài khoản đang chờ Ban chủ nhiệm duyệt trước khi sử dụng."*
2. **`07-compare-api.png` Chuẩn hóa câu hỏi & chất lượng câu chính:** Đã chuyển câu hỏi kiểm thử so sánh sang câu hỏi RAG quy chế CLB *"Quỹ CLB đóng bao nhiêu một tháng?"*. Câu chính của model local trích dẫn chính xác mức đóng 50.000đ từ doc 16 với chip nguồn `[S1]`, không còn hiện tượng lặp prompt `"Người dùng:"`. Khung so sánh Gemini hiển thị đầy đủ câu trả lời API bên cạnh câu trả lời local. Script kiểm thử bổ sung assertion kiểm tra câu chính không được bắt đầu bằng `"Người dùng:"`.
3. **`04-chat-codefest.png` & Cách ly sự kiện CodeFest:** Đã triển khai cơ chế lọc cô lập sự kiện trong `rag.py` (`event_markers`). Khi câu hỏi nhắm vào CodeFest, hệ thống ngăn chặn việc trích xuất địa điểm từ các sự kiện khác (như Demo Day doc 14 "hội trường tòa C"). Câu trả lời trích xuất độc quyền *"Địa điểm: sảnh tòa B. [S1]"*. Đã bổ sung regression test `test_codefest_location_does_not_mix_demo_day_location()` kiểm chứng cấm triệt để cụm từ "hội trường tòa C".
4. **`11-pwa-mobile.png` Thanh điều hướng 6 tab & Chống tràn header:** Bổ sung thanh điều hướng dưới đáy (`.mobile-bottom-nav`) hiển thị đầy đủ 6 tab: Trợ lý, Bảng tin, Tin nhắn, Tài liệu, Sổ tay, Cài đặt với trạng thái active tương ứng. Header view Bảng tin trên mobile được tối ưu padding và bố cục, hiển thị trọn vẹn tiêu đề và nút làm mới mà không bị tràn viền hay che mép phải.
5. **Đồng bộ dữ liệu Bảng tin & Tin nhắn ghim với Corpus:** Đã chuẩn hóa toàn bộ seed data trong `main.py`, `club_chat.py` và `club_chat.db`:
   - Sinh hoạt CLB: Thứ Năm hằng tuần, 18:30–21:00, phòng A2-304 (khớp doc 03).
   - Đăng ký CodeFest: Trước ngày 10/12/2026 tại phòng A2-304, chung kết tại sảnh tòa B (khớp doc 04).
   - Đóng quỹ CLB: 50.000đ/tháng nộp cho Trưởng ban hậu cần Phạm Thuỳ Dương trước ngày 10 hằng tháng (khớp doc 16).
6. **Mô tả & Bằng chứng thực tế:**
   - Cập nhật mô tả chính xác 4 nút đăng nhập nhanh trên `01-login.png`: Chủ nhiệm CLB, Phó chủ nhiệm, Trưởng ban, Thành viên (không có CTV).
   - Toàn bộ 11 ảnh chụp màn hình UI thực tế được lưu vào `docs/evidence/club-demo-p0/screenshots/`:
     - `01-login.png`: Màn hình đăng nhập 4 role quick buttons (1280x850)
     - `02-chat-schedule.png`: Câu 1 (lịch & địa điểm sinh hoạt, trích dẫn doc 03 [S1])
     - `03-chat-fund.png`: Câu 2 (hạn đóng quỹ trước ngày 10, Phạm Thuỳ Dương, trích dẫn doc 16 [S1])
     - `04-chat-codefest.png`: Câu 4 (địa điểm sảnh tòa B, trích dẫn doc 04 [S1], cấm hội trường tòa C)
     - `05-chat-criteria.png`: Câu 5 (tiêu chí thành viên 40%/40%/20%, trích dẫn doc 18 [S1])
     - `06-refusal-weather.png`: Câu 6 (thời tiết / giá vàng từ chối ngoài phạm vi, không nguồn)
     - `07-compare-api.png`: Thẻ so sánh với Gemini API (model gemini-3.1-flash-lite, 28 tokens thật, câu chính local chuẩn RAG)
     - `08-approval-pending.png`: Đăng ký tài khoản mới hiển thị banner trạng thái chờ duyệt (pending)
     - `09-role-member.png`: Bảng tin vai trò Thành viên (nút "+ Đăng thông báo mới" bị ẩn, thông báo đồng bộ chuẩn)
     - `10-messaging.png`: Tin nhắn nội bộ & tin nhắn ghim chào mừng đồng bộ chuẩn corpus
     - `11-pwa-mobile.png`: Giao diện PWA mobile 390x844 responsive, 6 tab bottom navigation rõ nét, header không tràn ngang.
