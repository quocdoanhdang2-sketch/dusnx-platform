# DUSN-X bilingual behavior

`preferred_language` nhận `auto`, `vi`, `en` và tương thích client cũ. Rule detector ưu tiên dấu/từ
chức năng tiếng Việt, sau đó từ khóa tiếng Anh; câu ngắn dùng preference/session policy. Response
trả `detected_language` và `response_language`. Lệnh “Từ giờ trả lời bằng tiếng Anh” hoặc
“Please answer in Vietnamese from now on” supersede một memory `preference` toàn cục.

Provider nhận chỉ dẫn ngôn ngữ rõ. Tên riêng, ID, URL và code được giữ nguyên. Detector không phụ
thuộc LLM. UI lưu lựa chọn local khi chưa đăng nhập và gửi preference qua API; server memory chỉ
được tạo bởi câu lệnh lưu preference đã xác nhận qua response thành công.

Phần còn lại: dịch toàn bộ label/error UI thay vì chỉ các control chính; thêm các template tiếng
Anh cho mọi nhánh application rule; mở rộng runtime matrix I18N-01–12. Vì vậy đây là nền tảng
song ngữ đã chạy, chưa phải bản địa hóa hoàn chỉnh toàn sản phẩm.
