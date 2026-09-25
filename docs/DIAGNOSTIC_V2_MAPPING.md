# Mapping nguồn AI diagnostic V2

`diagnostic_benchmark_dataset_v2.md` được giữ để đối chiếu. Nguồn có 12 câu
trong 4 sequence, toàn bộ `ai_generated`, và cột Review chưa được Reviewer 2
xác nhận. Vì vậy file chuyển đổi là **AI diagnostic chưa được reviewer duyệt**,
không phải benchmark độc lập.

Tập 20 ca trước tại `benchmarks/benchmark_v1_ai_source_diagnostic.jsonl` được
giữ nguyên. V2 chạy riêng tại `benchmarks/benchmark_v2_ai_diagnostic.jsonl`.

## Quyết định mapping trước prediction

| ID | Quyết định | Lý do |
|---|---|---|
| D01-1 | Giữ `recommendation/conversation/recommend` | Route khớp taxonomy hiện có |
| D01-2 | Giữ intent `followup`, đổi action nguồn `reply` thành `clarify` | Train mapping hiện tại dùng `followup → conversation/clarify`; câu phụ thuộc lựa chọn trước và cần làm rõ đối tượng. Đây là quyết định kỹ thuật provisional, chưa phải reviewer approval |
| D01-3 | Giữ `presentation_edit/productivity/edit_slide` | Lệnh tạo nội dung slide trong PowerPoint |
| D02-1 | Giữ `research/search_rag/search` | Yêu cầu tìm bài báo |
| D02-2 | Giữ `summarize/productivity/summarize` | Cô đọng kết quả trước |
| D02-3 | Giữ `followup/conversation/clarify` | Yêu cầu làm rõ kết quả trước |
| D02-4 | Giữ `presentation_edit/productivity/edit_slide` | Lệnh tạo biểu đồ trong slide |
| D03-1 | Giữ `research/search_rag/search` | Yêu cầu tra cứu log; chỉ đánh giá routing, không chứng minh quyền truy cập log thật |
| D03-2 | Giữ `followup/conversation/clarify` | Thu hẹp yêu cầu trước; evaluator chỉ truyền latent state |
| D03-3 | Loại, chờ capability/nhãn | Yêu cầu render bảng log lên web; không có action UI/display trong constants. Không ép thành `reply` |
| S05_Diag-1 | Giữ `research/search_rag/search` | Yêu cầu tìm hiểu RAG |
| S05_Diag-2 | Giữ `recommendation/conversation/recommend`, đánh dấu post-hoc | Nhãn đã được bàn sau khi xem prediction tập cũ; chỉ dùng diagnostic nội bộ, không dùng làm bằng chứng độc lập |

D03 chỉ giữ prefix bước 1–2; không có bước sau phụ thuộc D03-3. D01 giữ đúng
`web → zalo → powerpoint`. D02 có các bước `web → web → zalo → powerpoint`,
trong đó tồn tại transition ba bước `web → zalo → powerpoint` ở bước 2–4.

## Giả định ngữ cảnh

- Tên trong cột State (`topic_list`, `search_results`, `error_logs`, v.v.) không
  được đưa vào request và không được biến thành state giả.
- Những câu nhắc bài báo, kết quả tìm kiếm, summary hoặc log chỉ kiểm tra routing
  và latent-state continuity. Evaluator không chứng minh dữ liệu đó đã được truy
  xuất, đọc, lọc hoặc hiển thị thật.
- Nguồn không có feedback quan sát được nên mọi `known_feedback_value` là `0.0`.
- Expected labels được khóa trước khi mở prediction; reviewer vẫn cần duyệt D01-2
  và toàn bộ nguồn. S05_Diag-2 phải luôn được xem là post-hoc diagnostic.
