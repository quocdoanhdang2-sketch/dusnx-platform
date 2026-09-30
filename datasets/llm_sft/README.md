# SFT tiếng Việt, bản thiết kế nhỏ

Các hội thoại **do AI soạn, chưa được người duyệt độc lập**; không phải hội thoại quan sát từ người dùng. Mọi tên và trí nhớ đều giả. Nội dung mới được dành cho sử dụng theo CC0-1.0; không chứa dữ liệu CSConDa, MASSIVE, SGD hoặc benchmark/router/reviewer v3. Mọi record dùng `source=synthetic_designed` và `review_status=needs_human_review`.

Mỗi dòng là một chuỗi đầy đủ. `scenario_family` là nhóm kịch bản thiết kế, tách giữa các split; không sinh hàng loạt bằng thay tên. `quality_contracts` ghi fact bắt buộc, fact obsolete/rejected bị cấm, fact tương lai và kiểu trả lời theo từng lượt. Validator đối chiếu completion với đúng prefix trước lượt đó. Trạng thái trong system là dữ liệu giả do ứng dụng cung cấp, không phải đáp án benchmark được nối vào prompt. Model học cách diễn đạt có căn cứ; cập nhật state thật vẫn do DUSN-X xử lý.

`test.jsonl` là **bản nháp AI thiết kế**, chưa đáp ứng điều kiện “do người viết”. Manifest khóa byte để kiểm tra thay đổi trong development; không đồng nghĩa nhãn đã được người duyệt. Một người cần viết bộ test mới theo [mẫu](../../docs/LLM_TEST_AUTHORING_TEMPLATE.md), người thứ hai duyệt, rồi khóa trước full train và trước khi xem prediction. Không dùng test để chọn hyperparameter.

Chạy `python python/scripts/prepare_llm_data.py` để kiểm tra checksum, schema, split, mọi prefix dùng train và lấy mẫu duyệt. Dữ liệu ít: dùng thử pipeline, chưa đủ bằng chứng triển khai model. Kiểm tra trùng prompt chính xác và khai báo nhóm kịch bản không thay thế duyệt trùng ngữ nghĩa bởi người.
