# Quy định Quản lý và Khai thác Máy chủ AI & Server GPU Lab C1-C5

## 1. Cơ sở vật chất và cấu hình phần cứng
Hệ thống máy chủ tính toán hiệu năng cao đặt tại phòng Lab C1-C5 do Ban Kỹ thuật CLB IT chịu trách nhiệm vận hành gồm:
- 01 Server Deep Learning: CPU AMD EPYC 32 cores, 128GB RAM, 02 Card đồ họa NVIDIA RTX 4090 24GB VRAM.
- 02 Trạm làm việc Data Science: CPU Intel Core i9, 64GB RAM, 01 Card NVIDIA RTX 3090 24GB VRAM.
- Hệ thống lưu trữ mạng NAS nội bộ 16TB tốc độ cao dành cho tập dữ liệu (datasets).

## 2. Đối tượng và điều kiện cấp quyền truy cập
- Đối tượng: Thành viên chính thức của CLB IT tham gia các đề tài nghiên cứu AI, các nhóm dự án chuẩn bị thi Hackathon CodeFest, hoặc đồ án tốt nghiệp được Ban chủ nhiệm phê duyệt.
- Điều kiện:
  1. Đã hoàn thành khóa học an toàn hệ thống và sử dụng Linux căn bản.
  2. Gửi đề xuất qua form đăng ký lịch GPU trước ít nhất 24 giờ.
  3. Được xác nhận cấp tài khoản SSH riêng biệt (không dùng chung tài khoản root).

## 3. Quy tắc sử dụng và thời gian phân bổ
- Mỗi phiên huấn luyện mô hình (Training Session) được đăng ký tối đa 06 tiếng liên tục vào ban ngày (08:00 - 18:00).
- Các tác vụ huấn luyện dài hạn (Overnight Training từ 21:00 đến 07:00 hôm sau) phải đăng ký trước với Ban quản trị Lab và cài đặt checkpoint tự động lưu lại trọng số.
- Khi sử dụng card GPU, người dùng phải theo dõi tài nguyên bằng lệnh `nvidia-smi` hoặc `nvtop`, không được chiếm dụng bộ nhớ VRAM khi không thực thi tính toán.
- Sau khi hoàn thành phiên làm việc, thành viên phải giải phóng tài nguyên (kill process) và dọn dẹp các tệp tạm (temporary files) trong thư mục `/tmp`.

## 4. Các hành vi nghiêm cấm và hình thức kỷ luật
- Nghiêm cấm tuyệt đối sử dụng máy chủ CLB để đào tiền điện tử (crypto mining), tấn công mạng, quét cổng hoặc lưu trữ văn hóa phẩm độc hại.
- Nghiêm cấm chia sẻ thông tin đăng nhập hoặc mở cổng ra ngoài Internet (port forwarding) khi chưa được phép của Trưởng ban Kỹ thuật.
- Vi phạm lần đầu: Tạm khóa tài khoản truy cập server trong 14 ngày.
- Vi phạm lần hai hoặc vi phạm nghiêm trọng: Tước quyền truy cập vĩnh viễn, đưa ra hội đồng kỷ luật CLB và kiến nghị trừ điểm rèn luyện sinh viên.
