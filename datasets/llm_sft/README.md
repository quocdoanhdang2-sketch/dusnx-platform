# SFT tiếng Việt, bản thiết kế nhỏ

Các hội thoại **do AI soạn, chưa được người duyệt độc lập**; không phải hội thoại quan sát từ người dùng. Mọi tên và trí nhớ đều giả. Nội dung mới được dành cho sử dụng theo CC0-1.0; không chứa dữ liệu CSConDa, MASSIVE, SGD hoặc benchmark/router/reviewer v3.

Mỗi dòng là một chuỗi đầy đủ. `scenario_family` là nhóm kịch bản thiết kế, tách giữa các split; không sinh hàng loạt bằng thay tên. Các câu trả lời trợ lý chỉ biết những lượt trước đó. Trạng thái trong system là dữ liệu giả do ứng dụng cung cấp, không phải đáp án benchmark được nối vào prompt. Model học cách diễn đạt có căn cứ; cập nhật state thật vẫn do DUSN-X xử lý.

`test.jsonl` là **bản nháp AI thiết kế**, chưa đáp ứng điều kiện “do người viết”. Manifest khóa byte trước train; không đồng nghĩa nhãn đã được người duyệt. Một người cần tự viết/kiểm tra bộ test, cập nhật manifest trước full train và không xem prediction trước khi khóa. Không dùng test để chọn hyperparameter. Không được tuyên bố kết quả độc lập trên bản nháp này.

Chạy `python python/scripts/prepare_llm_data.py` để kiểm tra checksum, schema, split, mọi prefix dùng train và lấy mẫu duyệt. Dữ liệu ít: dùng thử pipeline, chưa đủ bằng chứng triển khai model. Kiểm tra trùng prompt chính xác và khai báo nhóm kịch bản không thay thế duyệt trùng ngữ nghĩa bởi người.
