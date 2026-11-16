# Quy chuẩn Git Flow và Code Review Ban Kỹ thuật CLB IT

## 1. Mục đích và phạm vi áp dụng
Tài liệu này quy định chuẩn mực quản lý mã nguồn, quy trình phân nhánh (Git Flow) và tiêu chuẩn đánh giá mã nguồn (Code Review) cho tất cả các dự án phần mềm do Ban Kỹ thuật CLB IT chủ trì hoặc hỗ trợ. Áp dụng cho 100% lập trình viên và cộng tác viên của CLB.

## 2. Quy tắc đặt tên nhánh (Branch Naming)
Mọi repository của CLB IT tuân thủ các quy tắc phân nhánh sau:
- Nhánh `main`: Chứa mã nguồn ổn định, sẵn sàng triển khai (Production/Release). Nghiêm cấm push trực tiếp lên `main`.
- Nhánh `develop`: Nhánh tích hợp cho giai đoạn phát triển hiện tại.
- Nhánh tính năng: `feature/<tên-tính-năng>` hoặc `feat/<mã-task>-<mô-tả-ngắn>` (ví dụ: `feature/auth-jwt`, `feat/tk-12-chat-ui`).
- Nhánh sửa lỗi: `bugfix/<mô-tả-lỗi>` hoặc `fix/<mã-task>` (ví dụ: `bugfix/scroll-leak`).
- Nhánh khẩn cấp: `hotfix/<phiên-bản>` (chỉ tạo từ `main` khi có sự cố nghiêm trọng).

## 3. Quy chuẩn viết thông điệp Commit (Conventional Commits)
Thông điệp commit phải viết bằng tiếng Anh hoặc tiếng Việt rõ ràng, theo định dạng `<loại>(<phạm vi>): <mô tả ngắn>`:
- `feat`: Tính năng mới cho người dùng.
- `fix`: Sửa lỗi phần mềm.
- `docs`: Thay đổi hoặc bổ sung tài liệu.
- `style`: Định dạng mã nguồn, thụt đầu dòng, dấu chấm phẩy (không đổi logic code).
- `refactor`: Tái cấu trúc code (không thêm tính năng, không sửa bug).
- `test`: Thêm hoặc cập nhật unit test, integration test.
- `chore`: Cập nhật cấu hình build, package dependencies.

## 4. Quy trình Pull Request (PR) và Code Review
- Mọi thay đổi vào `develop` hoặc `main` phải thông qua Pull Request (PR).
- PR phải mô tả rõ: Vấn đề cần giải quyết, giải pháp kỹ thuật, ảnh chụp kết quả kiểm thử (screenshot/test log).
- Yêu cầu tối thiểu:
  1. Ít nhất 01 thành viên Ban Kỹ thuật (hoặc Trưởng ban Đỗ Nam Khánh / Lead Tech Lê Quốc Bảo) review và Approve.
  2. Toàn bộ bài kiểm thử tự động (CI test harness) phải chuyển sang trạng thái xanh (Passed 100%).
  3. Không có conflict với nhánh đích trước khi merge.
- Thời gian phản hồi review: Không quá 24 giờ kể từ khi mở PR.

## 5. Tiêu chuẩn chất lượng mã nguồn
- Code phải có chú thích (docstring/comments) cho các hàm xử lý nghiệp vụ phức tạp.
- Tuân thủ nguyên tắc Clean Code và SOLID.
- Tuyệt đối không commit thông tin nhạy cảm: API Keys, Token JWT, Mật khẩu cơ sở dữ liệu (sử dụng file `.env` và `.gitignore`).
- Mỗi hàm không quá 60 dòng lệnh; độ phức tạp Cyclomatic dưới 10.
