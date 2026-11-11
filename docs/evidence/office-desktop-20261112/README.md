# Bằng chứng Office Desktop + Web UI — 2026-11-12

Bằng chứng chạy **Word Desktop, PowerPoint Desktop và Web UI thật** với task pane Office.js
sideload, Gateway local và provider Gemini. Tài khoản là user tổng hợp; file văn bản/trình chiếu
là artifact test cục bộ. Không có token, mật khẩu, cookie, dữ liệu người dùng thật hay secret nào
trong thư mục này.

## Môi trường

| Thành phần | Giá trị |
|---|---|
| Ứng dụng | Microsoft 365 Apps, Word & PowerPoint `16.0.20527.20150`, platform `x64` |
| Task pane | `https://localhost:3001/word-taskpane.html` và `https://localhost:3001/taskpane.html` |
| Manifest | sideload theo user trong `HKCU\Software\Microsoft\Office\16.0\WEF\Developer` |
| HTTPS server | `word-addin/dev-server.js`: same-origin, CSP, `no-store`, proxy `/v1/*` về Gateway |
| Gateway / AI API | `http://127.0.0.1:8080` / `http://127.0.0.1:8000` (uvicorn loopback) |
| Web UI | `http://127.0.0.1:8080` (Chrome) |
| Provider | Gemini `gemini-3.1-flash-lite` qua endpoint OpenAI-compatible, fallback Ollama |
| Tài khoản | `officedesk1211` (Word/PowerPoint), `timeline_evidence_20261112` (telemetry) — user tổng hợp |

Mật khẩu tài khoản tổng hợp không nằm trong repo; thông tin đăng nhập phục vụ chụp telemetry
được giữ ngoài workspace.

## Kết quả

### 1. Word — chèn bảng native

![Form chèn bảng trong Word](word-desktop-table-form.png)
![Proposal bảng trong Word](word-desktop-table-proposal.png)
![Bảng đã chèn trong Word](word-desktop-table-inserted.png)

Output `Table`, Apply mode `Replace selected text`, instruction mô tả bảng ưu/nhược điểm làm việc
nhóm (chỉ định tính, không có số liệu). Pane hiện proposal để review; sau khi Apply, trạng thái
`Table inserted at the cursor.` và văn bản có bảng native 6 hàng × 2 cột.

Trên build Word này `Range.insertTable` / `Selection.insertTable` trả `InvalidArgument`; add-in
dựng HTML bảng đã escape rồi `insertHtml`, host tạo bảng native. Đường dẫn này có unit test riêng.

### 2. Word — chặn ghi khi bật Track Changes

![Track Changes guard](word-desktop-track-changes-guard.png)

Bật **Review > Track Changes** bằng chính control ribbon, kiểm tra lại bằng COM
(`TrackRevisions = True`), rồi tạo proposal và Apply. Add-in đọc `document.changeTrackingMode`
(WordApi 1.5), từ chối ghi, xóa draft và giữ nguyên văn bản:
`Track Changes is on. Turn it off (Review > Track Changes) and create a new proposal; the draft was discarded.`
COM so sánh text trước/sau xác nhận tài liệu không đổi.

### 3. PowerPoint — chèn bảng native từ outline

![Proposal bảng PowerPoint](powerpoint-desktop-table-proposal.png)
![Bảng đã chèn PowerPoint](powerpoint-desktop-table-inserted.png)
![Undo lần chèn bảng](powerpoint-desktop-table-undo.png)

Mode `Generate slides from instruction`, layout `Title + native table (PowerPointApi 1.8)`.
Sau Apply: `Inserted 1 slide(s) after slide 1.`, slide 2 là bảng native 5 hàng × 2 cột. Bấm
**Undo last slide insertion**: `Removed 1 inserted slide(s).`, deck trở lại 1 slide.

### 4. PowerPoint — chart native từ dữ liệu người dùng nhập

![Form chart PowerPoint](powerpoint-desktop-chart-form.png)
![Chart đã chèn](powerpoint-desktop-chart-inserted.png)
![Undo lần chèn chart](powerpoint-desktop-chart-undo.png)

**Office.js không có API tạo chart native.** Add-in không vẽ chart bằng shape và không để model
sinh số liệu. Người dùng nhập tay nhãn và giá trị (ví dụ `Q1 12.5`, `Q2 18`, `Q3 9.75`); AI API
dựng file một slide chứa chart native bằng OOXML (`POST /v1/office/chart-slide`), rồi add-in chèn
bằng `presentation.insertSlidesFromBase64` và kiểm tra đúng một slide được thêm. Trạng thái:
`Inserted one native chart slide after slide 1.`; slide hiển thị chart cột với chú thích
`DUSN-X · dữ liệu do người dùng nhập`. Undo trả deck về 1 slide.

Ảnh form chụp trên `test-deck.pptx`; ảnh chart và undo chụp trên `chart-result.pptx` với cùng bộ
dữ liệu đã nhập. Không có số liệu nào do model tạo ra trong chart.

### 5. Secret guard — Word và PowerPoint

![Secret guard Word](word-desktop-secret-form.png)
![Secret guard Word — từ chối](word-desktop-secret-guard.png)
![Secret guard PowerPoint](powerpoint-desktop-secret-guard.png)

Instruction chứa chuỗi giống API key bị chặn ngay tại client, trước khi gửi provider:
`The instruction looks like it contains an API key. Remove secrets before sending it to the provider.`
Guard kiểm tra cả instruction, selection, chart title và chart data.

### 6. Telemetry — sự kiện Word hiển thị trên Web UI

![Timeline Web UI](webui-desktop-timeline.png)

Sau khi Apply một proposal text trong Word dưới tài khoản `timeline_evidence_20261112`, add-in
gửi `POST /v1/me/events` với `platform=word`. Web UI hiển thị 2 sự kiện mới nhất:
`word · apply · Applied rewrite text (20 characters)` và `web · chat_message` của cùng session,
kèm intent/agent/state version/confidence. Dữ liệu lấy từ `GET /v1/me/events` bằng token của
chính tài khoản đó.

## Lỗi thật đã tìm và sửa trong đợt này

- **Word telemetry 500:** `POST /v1/me/events` với `platform=word` làm FastAPI trả 500 vì
  `PLATFORM_TO_ID` chỉ có `web/zalo/powerpoint`. Sửa: platform lạ dùng bucket `web` cho suy luận,
  storage vẫn giữ tên thật; thêm regression test `python/tests/test_platform_bucket.py`.
- **Timeline trống khi mở view:** `showView('timeline')` chỉ bật view mà không gọi
  `loadTimeline()`, nên trang trắng cho tới khi bấm "Làm mới Timeline". Sửa trong
  `web-ui/app.js`; thêm lựa chọn lọc `word` vào filter nền tảng.

## Kiểm thử tự động đi kèm

- `python/tests/test_platform_bucket.py` — platform chưa huấn luyện dùng bucket `web`.
- `python/tests/test_office_charts.py` — validate chart request và dựng slide chart native.
- `node --test word-addin/word-taskpane.test.js` và `powerpoint-addin/taskpane.test.js` — guard,
  proposal/apply, undo, secret, chart parsing.

## Ghi chú trung thực

- Ảnh chụp bằng `PrintWindow` từ cửa sổ Word/PowerPoint/Chrome thật; trạng thái và số slide/bảng
  được xác nhận thêm bằng COM/UIA trong các script `runtime/office-desktop-20261112/*.py`.
- Nội dung bảng do model sinh là **mô tả định tính**, không chứa số liệu bịa; chart chỉ dùng số
  người dùng nhập.
- Các vệt đỏ trong ảnh Word là gạch chân spell-check tiếng Việt, không phải tracked changes.
- Bằng chứng chứng minh tích hợp, guard và telemetry hoạt động trên Desktop thật; không chứng
  minh chất lượng nội dung do model sinh.
