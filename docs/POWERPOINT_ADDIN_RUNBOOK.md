# PowerPoint Add-in runbook

Task pane dùng Office.js PowerPointApi 1.5 (cần getSelectedShapes), đăng nhập DUSN-X bằng
opaque token chỉ giữ trong RAM, chọn/tạo session, đọc đúng một text shape đang chọn,
gửi qua `/v1/chat`, hiển thị proposal/provenance và chỉ ghi sau khi người dùng bấm Apply.

1. Chạy DUSN-X Gateway tại `http://localhost:8080` và xác minh `/v1/health`.
2. Cài certificate localhost tin cậy bằng công cụ Office Add-in của Microsoft hoặc certificate
   nội bộ; phục vụ thư mục `powerpoint-addin` bằng HTTPS tại cổng 3001.
3. Xác minh `https://localhost:3001/taskpane.html`, rồi sideload `manifest.xml` trong PowerPoint.
4. Đăng nhập bằng tài khoản test, chọn đúng một Text Box có text, tạo proposal,
   kiểm provenance và text mới rồi bấm Apply. Không chọn nhiều slide/shape.

Apply từ chối khi đổi slide/shape, sửa text gốc, đổi session/logout, proposal rỗng,
chỉ là metadata, không thay đổi text hoặc không có provenance LLM thực. Lúc request
đang chạy, không tạo request/Apply chồng nhau. Không fallback sang shape đầu tiên.
Office cũ chưa hỗ trợ requirement set 1.5 cần nâng cấp; không tự hạ guard để chạy.

## Kiểm chứng Desktop còn cần người dùng

1. Tạo tài liệu test có hai Text Box trên mỗi slide; chọn Text Box thứ hai.
2. Create proposal: xác nhận tài liệu **chưa đổi**, chỉ task pane hiện nội dung đề xuất.
3. Apply: chỉ Text Box thứ hai thay đổi; kiểm Undo và chạy thử lại.
4. Tạo proposal mới rồi lần lượt đổi slide, đổi shape, sửa text gốc: Apply phải từ chối.
5. Tạo proposal rồi logout; thử provider offline và selection không phải text.
   Không được ghi slide hoặc báo thành công giả.
6. Ghi version Office/requirement set và kết quả thật; không dùng mock để đánh dấu Desktop đạt.

Cloud kiểm HTTP OPTIONS từ origin https://localhost:3001 và phục vụ taskpane.html qua
HTTPS bằng CA cục bộ có xác minh. Điều đó không chứng minh Office WebView trên Windows
đã tin cậy certificate hoặc cho phép kết nối HTTP localhost Gateway. Nếu WebView chặn,
dùng reverse proxy HTTPS cho Gateway, đặt DUSNX_GATEWAY về URL đó và cấu hình CORS
đúng origin; không tắt kiểm tra TLS hoặc đưa token vào URL.

Không đưa token vào URL/log/repo. Nếu Office API hoặc ghi shape thất bại, UI báo lỗi và không báo
đã áp dụng. Agent đã chạy mock/unit và validate XML; native Desktop cần người dùng có PowerPoint.
