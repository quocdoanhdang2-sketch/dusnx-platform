# Club IT Assistant — P0 Acceptance (2026-11-20)

Branch: `fix/club-demo-p0` (HEAD `bc82b81` + working-tree fixes, not committed)
Runtime: club stack `:8010` / `:8090`; production `:8000` / `:8080` untouched.

## Runtime identity (read from `/health`)

| Item | Value |
|---|---|
| AI API | `status=ok`, `provider=ollama` |
| Model | `configured_model=dusnx-vi-club`, `model_available=true` |
| `rag.py` sha256 | `3eb63ff7c2ba30434455fdecf358b2b3f41814ed0551908e01bfc2673d34962c` |
| RAG index | `runtime/club-rag/rag.db`, 26 documents / 225 chunks |
| Gateway | `service=dusnx-gateway`, `ai_api_url=http://127.0.0.1:8010`, binary `51bd76fb…` |

## Offline gates

| Suite | Result |
|---|---|
| `pytest -q` (python/) | **488 passed, 1 skipped** (104.42 s) |
| `node --test web-ui/app.test.js web-ui/auth.test.js` | **24 / 24 passed** |
| Club harness, 28 cases (`cases_sha256 45778b9…`) | answer 20: hit@1/3/5 **1.0**, scoped gate **1.0**, grounded-or-abstained **1.0**, citation **1.0**; refuse 8: **1.0** |
| Repo-index harness, 16 cases (repo `rag.db`) | hit@1 **1.0**, hit@k **1.0**, MRR **1.0**, gate **1.0**, citation OK, 13 extractive answers, 4/4 negatives rejected |

The two indices are measured separately; club metrics must not be quoted for the repo index, or vice versa.

## Live acceptance — 3 consecutive runs on `:8090`

| Run | Timestamp (UTC) | Cases | API provider / model | Tokens | API latency | Primary answer |
|---|---|---|---|---|---|---|
| 1 | 2026-11-20T13:31:27Z | **12 / 12** | `openai` / `gemini-3.1-flash-lite` | 92 | 2,547 ms | `ollama` |
| 2 | 2026-11-20T13:31:46Z | **12 / 12** | `openai` / `gemini-3.1-flash-lite` | 94 | 1,688 ms | `ollama` |
| 3 | 2026-11-20T13:31:57Z | **12 / 12** | `openai` / `gemini-3.1-flash-lite` | 91 | 1,531 ms | `ollama` |

- Logs: `docs/evidence/club-demo-p0/run_1.log` … `run_3.log`.
- The comparison block reached the external API in all three runs; the club model stayed the primary answer source.
- Secret scan of the logs found only token counts, no credentials.

## Resolved & Verified Fixes

1. **CASE-11 capability reply resolved:** “Bạn làm được gì cho mình?” nay được trả lời tất định bằng mẫu năng lực CLB (tra cứu 26 văn bản có trích dẫn `[S#]`, từ chối ngoài phạm vi, sổ tay cá nhân, so sánh API). Script kiểm tra đã siết chặt: yêu cầu chứa "tài liệu", "nguồn", cấm chuỗi "Người dùng:", và `expect_provider_called: false`. Cả 3 lượt test live đều PASS tuyệt đối.
2. **External API compare:** Cả 3 lượt đều gọi thành công Gemini 3.1 Flash-Lite, token thật, độ trễ 1.5–2.5s.
3. **Screenshots & Rehearsal:** Đã diễn thành công trên UI thực tế và lưu đủ 11 ảnh minh chứng vào `docs/evidence/club-demo-p0/screenshots/`:
   - `01-login.png`: Màn hình đăng nhập 4 role quick buttons
   - `02-chat-schedule.png`: Câu 1 (lịch & địa điểm sinh hoạt, trích dẫn doc 03)
   - `03-chat-fund.png`: Câu 2 (hạn đóng quỹ trước ngày 10, Phạm Thuỳ Dương, trích dẫn doc 16)
   - `04-chat-codefest.png`: Câu 4 (địa điểm sảnh tòa B, trích dẫn doc 04)
   - `05-chat-criteria.png`: Câu 5 (tiêu chí thành viên 40%/40%/20%, trích dẫn doc 18)
   - `06-refusal-weather.png`: Câu 6 (thời tiết / giá vàng từ chối ngoài phạm vi, không nguồn)
   - `07-compare-api.png`: Thẻ so sánh với Gemini API (model gemini-3.1-flash-lite, token thật)
   - `08-approval-pending.png`: Đăng ký tài khoản mới ở trạng thái chờ duyệt (pending)
   - `09-role-member.png`: Tài khoản sau khi được duyệt vai trò Thành viên (bị ẩn nút đăng thông báo)
   - `10-messaging.png`: Tin nhắn nội bộ (kênh ban chuyên môn, gửi tin và ghim tin)
   - `11-pwa-mobile.png`: Giao diện PWA mobile 390x844 responsive, 6 tab không tràn ngang
