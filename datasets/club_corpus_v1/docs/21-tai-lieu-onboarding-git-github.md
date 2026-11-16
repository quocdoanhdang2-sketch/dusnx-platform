# Cẩm nang Hướng dẫn Git và GitHub căn bản cho Tân thành viên

## 1. Chuẩn bị môi trường
Tân thành viên gia nhập CLB IT bắt buộc hoàn thành các bước thiết lập công cụ làm việc trong 3 ngày đầu tiên sau khi nhận mã thành viên:
1. Cài đặt Git phiên bản mới nhất từ trang chủ `git-scm.com`.
2. Cấu hình thông tin tác giả cá nhân:
   ```bash
   git config --global user.name "Họ và Tên (Mã TV)"
   git config --global user.email "email-cua-ban@gmail.com"
   ```
3. Tạo cặp khóa SSH Key và liên kết tài khoản GitHub của bạn với Tổ chức (Organization) `CLB-IT-University`.
4. Tham gia kênh Discord/Slack nội bộ của Ban Kỹ thuật để nhận thông báo phân quyền repository.

## 2. Các lệnh thao tác hàng ngày
- Cập nhật mã nguồn mới nhất từ nhánh chính:
  ```bash
  git checkout develop
  git pull origin develop
  ```
- Tạo nhánh làm việc cá nhân cho tính năng mới:
  ```bash
  git checkout -b feature/ten-tinh-nang
  ```
- Kiểm tra trạng thái và lưu lại công việc:
  ```bash
  git status
  git add .
  git commit -m "feat(ui): them nut xem truoc tai lieu"
  ```
- Đẩy nhánh lên kho GitHub và tạo Pull Request:
  ```bash
  git push -u origin feature/ten-tinh-nang
  ```

## 3. Xử lý xung đột mã nguồn (Merge Conflict)
Khi gặp thông báo xung đột mã nguồn:
1. Giữ bình tĩnh, không xóa thư mục dự án làm lại từ đầu.
2. Mở trình soạn thảo mã nguồn (VS Code/Cursor) để quan sát các vùng đánh dấu `<<<<<<< HEAD`, `=======`, `>>>>>>>`.
3. Trao đổi trực tiếp với tác giả đoạn code xung đột trước khi chọn giữ bản nào (Accept Current Change / Incoming Change / Both).
4. Chạy lại toàn bộ test suite để đảm bảo hệ thống không bị gãy sau khi giải quyết xung đột.
5. Tạo commit hoàn tất xung đột và thông báo lên kênh trao đổi của nhóm.

## 4. Trợ giúp kỹ thuật
Nếu gặp khó khăn trong quá trình làm việc với Git, thành viên có thể liên hệ trực tiếp Trưởng ban Kỹ thuật hoặc tham gia buổi Office Hours vào chiều Thứ Bảy hàng tuần tại phòng Lab A2-305.
