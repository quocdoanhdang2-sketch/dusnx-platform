# Rà nội dung development SFT v2.1

Phạm vi là 43 record train và 12 record validation trong `datasets/llm_sft`. Không đọc hoặc chạy prediction trên holdout v3. Đây là rà soát của tác giả code đối với dữ liệu AI thiết kế, không phải human review độc lập; mọi record vẫn giữ `needs_human_review`.

| ID | Lỗi quan sát | Thay đổi | Lý do |
|---|---|---|---|
| `train-006` | Đáp án tự giới hạn yêu cầu “tối đa hai ý” vào “cuộc trao đổi này”, dù user không nêu phạm vi. | Bỏ phạm vi tự thêm; contract yêu cầu “tối đa hai ý” và cấm sở thích cũ “trả lời dài”. | Model chỉ bám yêu cầu mới; ứng dụng quyết định việc lưu lâu dài. |
| `train-017` | Lời kể của user rằng ứng dụng đã xác nhận bị dùng như state có thẩm quyền. | Chuyển quyết định tháng bảy vào system context với provenance “do ứng dụng cung cấp”; user chỉ yêu cầu nhắc lại. | Tách state xác thực khỏi lời kể chưa kiểm chứng trong hội thoại. |
| `train-020` | Context “chưa xác nhận lưu” chưa nói rõ DB chưa chạy, dễ mâu thuẫn với luồng sản phẩm đã lưu thành công. | Context ghi rõ yêu cầu chưa đi qua luồng ghi DB và chưa có kết quả lưu; đáp án không nhận đã lưu. | Chỉ dạy model từ chối xác nhận khi thực sự chưa có kết quả persistence. |
| `train-025` | User yêu cầu tóm tắt ba rủi ro nhưng prefix không cung cấp rủi ro; đáp án tự bịa nội dung. | Đưa ba rủi ro vào context và thêm cả ba vào `required_facts`. | Giữ mục tiêu học phạm vi sở thích tạm thời mà không dạy hallucination. |

Rà tiếp 39 train record còn lại và 12 validation record không phát hiện thêm trường hợp cùng loại. Các câu kiến thức mở hoặc yêu cầu sáng tạo có thể sinh nội dung mới; các câu hỏi state/memory đóng phải bám `quality_contracts` và context trước lượt trả lời.

Audit exact tokenizer sau sửa: train 94–187 token, trung bình 133.02; validation 115–145, trung bình 126.58; test AI nháp 101–142, trung bình 123.33. Không prompt trùng chính xác; near-duplicate cross-split lớn nhất 0.6731 dưới ngưỡng 0.82. Manifest development SHA-256: `8f97323ff91156d9c13b12845fed2585ee3149da76141bd5fbdeabfe7900f40a`.
