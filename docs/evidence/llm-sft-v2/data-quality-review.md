# LLM SFT v2 quality review

Review hiện tại là kiểm tra tự động/AI, không phải independent human review. Bộ draft bao phủ
12 family được yêu cầu và hai ngôn ngữ, nhưng câu trả lời chủ yếu kiểm thử “không có memory →
nói chưa biết và hỏi lại”. Các family false-save, supersede, pending, cross-platform và retry
mới có metadata phân loại, chưa có hội thoại nhiều lượt đủ giàu để train hành vi tương ứng.

Không dùng bộ này để train candidate v2, chọn config hoặc promotion. Người duyệt cần viết lại
tình huống nhiều lượt, đánh dấu obsolete/rejected/future facts, kiểm bản dịch không tạo case test
độc lập, sau đó khóa test trước prediction. Không sao chép hoặc paraphrase tám test v1 đã xem.
