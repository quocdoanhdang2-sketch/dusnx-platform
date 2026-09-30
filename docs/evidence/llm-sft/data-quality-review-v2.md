# Review dữ liệu SFT v2

Phạm vi chỉ gồm `datasets/llm_sft`; không đọc holdout/gold/blind/reviewer/output v3. So sánh bản v1 ở commit `f9caa0a` với dữ liệu development v2.

## Phát hiện ở v1 và cách sửa

- `train-015` nhắc lại “nền tối” trong câu hỏi lựa chọn sau khi người dùng đã rút sở thích đó. Câu mới chỉ nói chưa có lựa chọn và hỏi muốn chọn giao diện nào; contract cấm fact obsolete.
- `train-017` gọi lịch tháng bảy đã xác nhận là “dự kiến”, làm yếu trạng thái quyết định. Câu mới nói rõ lịch hiện hành là tháng bảy và cấm tháng sáu.
- Khi rà bản v2, câu “bản nháp thứ ba” từng bị completion hiểu thành thứ ba trong tuần. Input được sửa thành “gửi bản nháp vào thứ ba” để reference không suy diễn một nghĩa không có căn cứ.
- V1 không có nhãn máy đọc được cho fact hiện hành, obsolete, future hoặc kiểu clarification. V2 thêm contract theo từng assistant turn và test phá dữ liệu để chứng minh validator bắt lỗi.
- Không thấy assistant completion tiếng Anh trong v1. Hai user prompt tiếng Anh là tình huống chủ ý; reference vẫn tiếng Việt. V2 giữ dạng kiểm tra này ở các family riêng.
- Không xác nhận được lỗi fact không có trong context ở các case memory cũ. Các câu kiến thức mở như cache/cầu vồng không phải memory grounding. V2 phân biệt bằng contract: fact đóng phải có trong prefix; kiến thức mở có danh sách required fact rỗng và vẫn cần người duyệt.

## Kết quả v2

- Train: 43 chuỗi, 49 cặp; validation: 12/12; test AI nháp: 6/6. Tổng 61 chuỗi, 67 cặp, 61 scenario family.
- 100% nguồn `synthetic_designed`, revision `llm-authored-v2`, CC0-1.0, `needs_human_review`; không có dòng nào nhận là human-reviewed.
- Prompt exact duplicate: 0. Near-duplicate cross-split lớn nhất 0.6731, dưới ngưỡng 0.82. Hai cặp trên ngưỡng trong cùng train là prefix liên tiếp của cùng chuỗi nhiều lượt.
- Exact Qwen tokenizer revision `7ae557604adf67be50417f59c2c2f167def9a775`: train 94–187 token, validation 115–145, test 101–142; không completion nào chạm giới hạn 512.
- Phân bố train: 28 answer, 18 clarify, 3 acknowledge. Validation: 7 answer, 5 clarify. Test nháp: 4 answer, 2 clarify.

Audit tự động không thể chứng minh mọi câu tự nhiên hoặc mọi paraphrase đều đúng. Một người vẫn phải đọc đủ train/validation; test chính thức phải do người khác viết và được reviewer khác duyệt trước prediction.
