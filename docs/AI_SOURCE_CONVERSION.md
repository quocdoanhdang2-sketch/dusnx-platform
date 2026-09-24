# Chuyển đổi nguồn AI đa nền tảng

File `independent_benchmark_dataset.md` được giữ nguyên để đối chiếu với file
đính kèm. Dù tiêu đề nguồn dùng từ “Independent”, chính nội dung xác nhận toàn bộ
23 bước là `ai_generated`. Vì vậy đây là **nguồn AI chẩn đoán**, không phải
benchmark độc lập do người viết hoặc kết quả nghiên cứu.

Nguồn có 23 bước trong 7 sequence. Taxonomy runtime hiện chỉ hỗ trợ:

- intent: `chat`, `research`, `summarize`, `presentation_edit`,
  `recommendation`, `followup`;
- agent: `conversation`, `search_rag`, `productivity`;
- action: `reply`, `search`, `summarize`, `edit_slide`, `recommend`, `clarify`.

Các tên agent/action chi tiết trong Markdown chỉ được collapse khi ngữ nghĩa route
khớp rõ với taxonomy hiện có. Chúng không được thêm giả vào constants.

## Bảng quyết định chuyển đổi

| ID | Kết quả | Route hoặc lý do |
|---|---|---|
| S01-1 | Chuyển | `research/search_rag/search` |
| S01-2 | Chuyển | `summarize/productivity/summarize`; evaluator dùng latent state thật, không tạo `search_results` giả |
| S01-3 | Loại | Yêu cầu `ZaloAgent/send_message`; dự án không có agent/action gửi tin |
| S02-1 | Chuyển | `recommendation/conversation/recommend` |
| S02-2 | Chuyển | `presentation_edit/productivity/edit_slide` |
| S02-3 | Chuyển | `presentation_edit/productivity/edit_slide` |
| S03-1 | Chuyển | `chat/conversation/reply` |
| S03-2 | Chuyển | `recommendation/conversation/recommend` |
| S03-3 | Chuyển | `research/search_rag/search` |
| S04-1 | Chuyển | `research/search_rag/search` |
| S04-2 | Chuyển | `presentation_edit/productivity/edit_slide` |
| S04-3 | Chuyển | `presentation_edit/productivity/edit_slide` |
| S05-1 | Chuyển | `summarize/productivity/summarize` |
| S05-2 | Chuyển | `research/search_rag/search` |
| S05-3 | Loại, cần quyết định | Trộn tìm khóa học với recommendation; `search_courses` không được hỗ trợ. Cần chọn `research/search` hoặc `recommendation/recommend` trước khi đưa vào chạy |
| S06-1 | Chuyển | `chat/conversation/reply` |
| S06-2 | Chuyển | `presentation_edit/productivity/edit_slide` |
| S06-3 | Chuyển | `presentation_edit/productivity/edit_slide` |
| S07-1 | Chuyển | `research/search_rag/search` |
| S07-2 | Chuyển | `summarize/productivity/summarize` |
| S07-3 | Chuyển | `presentation_edit/productivity/edit_slide` |
| S07-4 | Chuyển | `presentation_edit/productivity/edit_slide` |
| S07-5 | Loại | Yêu cầu `ZaloAgent/send_message`; dự án không có agent/action gửi tin |

File chạy là `benchmarks/benchmark_v1_ai_source_diagnostic.jsonl`, gồm 20 bước
chuyển được. Khi loại S01-3, S05-3 và S07-5, các prefix còn lại vẫn liên tục nên
không cần tạo state hoặc câu mới. Tất cả `known_feedback_value` là `0.0` vì nguồn
không cung cấp feedback quan sát được.

Độ phủ intent của file chạy không có `followup`, vì cả hai dòng nguồn mang nhãn
đó đều yêu cầu action gửi Zalo chưa hỗ trợ. Không có chuỗi
`web → zalo → powerpoint` ba bước đúng thứ tự trong nguồn; không bổ sung câu mới
để tạo coverage giả.
