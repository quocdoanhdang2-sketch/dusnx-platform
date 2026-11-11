# PowerPoint Add-in runbook

Task pane dùng Office.js PowerPointApi 1.5 (cần `getSelectedShapes` và `insertSlidesFromBase64`),
đăng nhập DUSN-X bằng opaque token chỉ giữ trong RAM, chọn/tạo session, gọi `/v1/chat` same-origin
qua dev server HTTPS, hiện proposal/provenance và chỉ ghi sau khi người dùng bấm Apply.

Các mode:

| Mode | Đầu vào | Ghi vào deck |
|---|---|---|
| Edit selected text | đúng một slide + một text shape đang chọn | thay text của shape đó |
| Generate slides from instruction | chỉ dẫn + số slide 1–6 + ngôn ngữ + layout | chèn N slide từ `deck-template.pptx` sau slide cuối |
| Generate slides — layout `table` | outline dạng bảng | slide chứa bảng native (PowerPointApi 1.8) |
| Native chart from user data | tiêu đề, loại chart, nhãn và giá trị người dùng nhập | slide chứa chart native, chèn bằng `insertSlidesFromBase64` |

## Chạy local

1. Chạy DUSN-X Gateway và AI API (`start-local.ps1`); xác minh `/health` của cả hai.
2. Chạy `word-addin/dev-server.js` bằng HTTPS tại cổng 3001. Server phục vụ
   `taskpane.html`, `taskpane.js`, `deck-template.pptx` và proxy `/v1/*` về Gateway
   loopback; trả `no-store`, `nosniff`, CSP `connect-src 'self'`, không chuyển cookie.
3. Mở `https://localhost:3001/taskpane.html` trong PowerPoint (sideload `manifest.xml`)
   hoặc trong trình duyệt để kiểm giao diện. Office WebView cần tin certificate localhost.
4. Đăng nhập bằng tài khoản test; không dùng tài khoản thật cho ảnh/bằng chứng.

Nếu Office WebView chặn HTTPS localhost, dùng reverse proxy HTTPS cho Gateway và đặt
`DUSNX_GATEWAY` về URL đó với CORS đúng origin; không tắt kiểm tra TLS, không đưa token
vào URL.

## Generate slides

1. Chọn mode **Generate slides from instruction**, số slide, ngôn ngữ, gõ chỉ dẫn.
2. Bấm **Create slide outline**. Pane yêu cầu provenance LLM thật, parse outline
   `# Title` / `- bullet`, kiểm 1–6 slide, 1–5 bullet, độ dài và ký tự điều khiển.
3. Đọc preview. Nếu số slide sai hoặc nội dung sai, tạo lại; pane không ghi gì trước Apply.
4. Bấm **Append slides to presentation**. Pane tải template same-origin, chèn đúng N slide
   sau slide cuối, điền `DUSN-X Title/Body/Footer`; lỗi giữa chừng sẽ xóa các slide đã chèn
   và báo lỗi.

Template contract: `powerpoint-addin/deck-template.pptx`, canvas 960×540 px, đúng bốn shape
tên `DUSN-X Accent`, `DUSN-X Title`, `DUSN-X Body`, `DUSN-X Footer`. Màu trong COM là BGR
(accent `0x6E760F` = #0F766E). Đổi template phải giữ tên shape và kích thước canvas; chạy
lại test và kiểm tra ảnh render.

## Edit selected text

1. Chọn đúng một Text Box có text trên đúng một slide. Không chọn nhiều slide/shape.
2. Bấm **Create proposal from selected text shape**; đọc proposal/provenance.
3. Bấm **Apply to original text shape**. Apply từ chối khi đổi slide/shape, sửa text gốc,
   đổi session/logout, proposal rỗng, chỉ là metadata, không thay đổi text hoặc không có
   provenance LLM thực. Không fallback sang shape đầu tiên.

Không tạo request/Apply chồng nhau. Khi request đang chạy, các nút bị khóa.

## Native table và chart

- Layout `table`: pane yêu cầu 2 cột × 1–6 hàng, dựng bảng native bằng `ShapeCollection.addTable`
  sau khi Apply; thiếu PowerPointApi 1.8 thì từ chối trước khi gọi provider.
- **Chart native:** Office.js không có API tạo chart. Add-in gửi nhãn/giá trị **người dùng nhập**
  tới `POST /v1/office/chart-slide`; AI API dựng file một slide chứa chart native (OOXML) và trả
  base64; add-in gọi `presentation.insertSlidesFromBase64`, kiểm đúng một slide được thêm rồi mới
  báo `Inserted one native chart slide ...`. Không có số liệu nào do model sinh.
- **Undo last slide insertion** xóa đúng slide vừa chèn; apply/undo gửi telemetry nội dung-free
  qua `/v1/me/events`.
- Instruction, selection, chart title/data giống secret bị chặn trước khi gọi provider.

## Đã kiểm chứng trên Desktop

Bằng chứng 2026-11-09:
[`docs/evidence/powerpoint-addin-generate-20261107`](../docs/evidence/powerpoint-addin-generate-20261107/README.md).
Bằng chứng 2026-11-12 (bảng, chart, Undo, telemetry, secret guard):
[`docs/evidence/office-desktop-20261112`](../docs/evidence/office-desktop-20261112/README.md).

- Sinh 3 slide vào deck trống: title/body/footer đúng, footer `1`–`3`.
- Append 3 slide sau slide 3 (outline inject bởi harness để kiểm riêng đường Apply):
  thứ tự giữ nguyên, footer `4`–`6`, không có slide thừa.
- Edit mode: chọn `DUSN-X Body`, proposal/provenance hiện trong pane, Apply ghi đúng shape,
  proposal bị xóa.
- Layout bảng: chèn 1 slide bảng native 5×2; Undo trả deck về 1 slide.
- Chart: nhập `Q1 12.5 / Q2 18 / Q3 9.75`, nhận slide chart native, Undo xóa đúng slide.
- Unit test phủ guard đổi slide/shape/text/session, Apply lần hai, rollback khi template
  thiếu shape, preamble/nhãn outline, giới hạn kích thước, parse chart và secret guard.

## Còn mở

- Chưa hỗ trợ chèn ảnh vào slide; chưa kiểm nhiều cửa sổ PowerPoint đồng thời.
- Model local (baseline `qwen2.5:1.5b-instruct`, candidate v3) chưa ổn định định dạng outline:
  có lần trả sai số slide hoặc đổi từ ngữ. Preview là bước bắt buộc; không tự Apply.
- Bằng chứng dùng candidate để chạy tích hợp; candidate không được promote, stack đã khôi
  phục baseline sau khi chụp.
- Không đưa token vào URL/log/repo. Nếu Office API hoặc ghi shape thất bại, UI báo lỗi và
  không báo đã áp dụng.
