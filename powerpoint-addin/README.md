# PowerPoint task pane hiện tại

Đăng nhập qua Gateway bằng opaque token trong RAM, dùng `/v1/chat` và cùng SQLite
memory/session với Web. Không còn mô tả task pane hiện tại là client polling job
legacy. Xem [runbook](../docs/POWERPOINT_ADDIN_RUNBOOK.md).

Yêu cầu PowerPointApi 1.5 để lấy **shape đang chọn**, không tự chọn shape có chữ đầu
tiên. Proposal không ghi tài liệu. Apply chỉ ghi khi slide ID, shape ID, text gốc
và session vẫn khớp; proposal phải là text không rỗng, khác bản gốc và có provenance
LLM hợp lệ. Logout/session change làm mất hiệu lực proposal cũ.

Đã kiểm tra Office mock, HTTPS localhost và CORS trong cloud. Chưa xác minh PowerPoint
Desktop; không có certificate được cài vào hệ thống hoặc add-in được sideload ở đây.
Không đưa secret hoặc token vào URL, source hay log.
