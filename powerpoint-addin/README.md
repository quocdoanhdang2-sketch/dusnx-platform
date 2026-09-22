# PowerPoint connector — Phase 1

Thư mục này là connector skeleton để chứng minh hợp đồng API với DUSN-X Gateway.
Nó gửi yêu cầu tạo dàn ý slide vào `POST /api/v1/presentations/generations`, sau đó
poll trạng thái job qua `GET /api/v1/jobs/{jobId}`.

## Trạng thái hiện tại

- Đã có manifest, task pane và luồng async job.
- Chưa đóng gói certificate HTTPS localhost và chưa tự động ghi nội dung vào slide.
- Web demo tại `http://localhost:3000` đã dùng cùng API để kiểm tra luồng này trước.

## Phase 2

1. Chạy task pane bằng HTTPS local trên cổng `3001`.
2. Sideload `manifest.xml` vào PowerPoint.
3. Dùng Office.js để tạo/chỉnh slide từ kết quả job.
4. Thay polling bằng SignalR nếu cần cập nhật tiến độ thời gian thực.

Không đưa secret hoặc access token Office vào source code hay commit GitHub.
