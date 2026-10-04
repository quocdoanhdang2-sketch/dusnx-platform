# PowerPoint Add-in runbook

Task pane dùng Office.js PowerPointApi 1.2, đăng nhập DUSN-X bằng opaque token chỉ giữ trong RAM,
chọn/tạo session, đọc text của slide đang chọn, gửi qua `/v1/chat`, hiển thị proposal/provenance
rút gọn và chỉ ghi vào text shape sau khi người dùng bấm Apply.

1. Chạy DUSN-X Gateway tại `http://localhost:8080` và xác minh `/v1/health`.
2. Cài certificate localhost tin cậy bằng công cụ Office Add-in của Microsoft hoặc certificate
   nội bộ; phục vụ thư mục `powerpoint-addin` bằng HTTPS tại cổng 3001.
3. Xác minh `https://localhost:3001/taskpane.html`, rồi sideload `manifest.xml` trong PowerPoint.
4. Đăng nhập bằng tài khoản test, chọn slide, tạo proposal, kiểm provenance, bấm Apply.

Không đưa token vào URL/log/repo. Nếu Office API hoặc ghi shape thất bại, UI báo lỗi và không báo
đã áp dụng. Agent đã chạy mock/unit và validate XML; native Desktop cần người dùng có PowerPoint.
