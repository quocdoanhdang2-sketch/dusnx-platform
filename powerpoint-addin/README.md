# PowerPoint task pane hiện tại

Đăng nhập qua Gateway bằng opaque token trong RAM, dùng `/v1/chat` và cùng SQLite
memory/session với Web. Xem [runbook](../docs/POWERPOINT_ADDIN_RUNBOOK.md).

Yêu cầu PowerPointApi 1.5 để lấy **shape đang chọn**, không tự chọn shape có chữ đầu
tiên. Có hai chế độ:

- **Edit selected text**: đọc đúng một slide + một text shape, gửi nội dung và chỉ dẫn,
  hiện proposal/provenance; Apply chỉ ghi khi slide ID, shape ID, text gốc và session
  vẫn khớp. Proposal phải là text không rỗng, khác bản gốc và có provenance LLM hợp lệ.
- **Generate slides from instruction**: gửi chỉ dẫn + số slide (1–6), nhận outline
  `# Title` / `- bullet` dạng chặt, hiện preview; Apply chèn N slide từ
  `deck-template.pptx` sau slide cuối hoặc sau slide đang chọn (tùy chọn), điền các
  shape có tên `DUSN-X Title`, `DUSN-X Body`, `DUSN-X Footer`. Vị trí được chốt lúc
  tạo preview; nếu slide đích bị xóa trước khi Apply, thao tác bị từ chối. Ảnh/template
  tải same-origin; lỗi chèn sẽ xóa các slide vừa thêm.

`insertSlidesFromBase64` chèn vào đầu deck, nên code chèn ngược với `targetSlideId`
rồi điền theo thứ tự deck. Parser bỏ qua preamble ngắn và nhãn `Slide N`/`Title:`/
`Bullet text:` do model sinh; từ chối code fence, JSON, sai số slide và vượt giới hạn
(6 slide, 5 bullet, 120/180 ký tự).

Logout/session change làm mất hiệu lực proposal cũ. Không đưa secret hoặc token vào
URL, source hay log.

Đã kiểm tra Office mock, HTTPS localhost, CORS và **PowerPoint Desktop thật** (Office.js
task pane, 16.0.20527): sinh 3 slide vào deck trống, append 3 slide sau slide 3 giữ
thứ tự, và sửa một text shape tại chỗ. Bằng chứng và hạn chế model:
[`docs/evidence/powerpoint-addin-generate-20261107`](../docs/evidence/powerpoint-addin-generate-20261107/README.md).
