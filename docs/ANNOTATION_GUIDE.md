# Duyệt nhãn không xem prediction

Reviewer chỉ nhận bản xuất sau và đọc toàn bộ chuỗi theo thứ tự. Không mở `predictions.jsonl`, `errors.json` hoặc báo cáo model trước khi chốt nhãn.

```bash
python python/scripts/review_labels.py --input benchmarks/holdout_v1.jsonl --output runtime/reviewer-A.jsonl --sequences 8
python python/scripts/review_labels.py --input runtime/prepared/train.jsonl --output runtime/train-review.jsonl --sequences 20
python python/scripts/review_labels.py --input runtime/reviewer-A.jsonl --compare runtime/reviewer-B.jsonl --output runtime/agreement.json
```

Điền reviewer là người thực; giữ nguyên record_id/sequence_id/step và điền `labels`:

- `active`: sự thật/quyết định người dùng đã xác nhận, còn hiệu lực sau bước hiện tại. Câu hỏi hoặc “nghe nói” không tạo quyết định.
- `obsolete`: thông tin đã được thay thế bằng xác nhận. Một đề nghị đổi chưa xác nhận không làm thông tin cũ obsolete; từ chối giữ nguyên active.
- `intent`: mục đích của bước, dựa trên ngữ cảnh đã có, không dùng feedback hoặc câu trả lời tương lai.
- `agent`: conversation, search_rag, productivity; ở benchmark API có thêm memory khi thực hiện lưu/sửa.
- `action`: reply/search/summarize/edit_slide/recommend/clarify; API memory dùng create_memory/await_confirm/update_memory/no_op.
- `requires_clarification`: true khi thiếu ngữ cảnh cần thiết, nhiều memory phù hợp hoặc phải xác nhận thay đổi; không tự đoán.

Router checkpoint có 6 intent trong `dusnx_core.constants`: chat, research, summarize, presentation_edit, recommendation, followup. Memory CRUD là luật ứng dụng, không phải đầu ra học được của checkpoint. Với nguồn ngoài chỉ có intent, để trống agent/action/state; không đoán cho đủ trường. Hỏi định nghĩa trực tiếp có thể là chat; yêu cầu tìm tài liệu/nguồn là research. Phải xem câu cụ thể, không chỉ tên label nguồn.

Phân biệt current recall, bỏ obsolete, clarification và chất lượng final answer. Keyword scorer chỉ là phép đo literal, có thể phạt cả câu phủ định tên cũ; reviewer semantic cần ghi riêng, không sửa gold vì thấy model sai. Từ được nêu trong giả định nhưng chưa từng lưu không phải obsolete theo nghĩa lịch sử; benchmark dùng `gold_obsolete_facts` như danh sách nhắc sai cần tránh, gồm cả claim chưa xác nhận, giới hạn này phải giữ khi đọc metric.

Script agreement yêu cầu hai reviewer khác nhau và cùng record IDs; xuất tỷ lệ đồng thuận, Cohen's kappa theo trường (null khi chỉ một lớp), từng bất đồng để phân xử. Danh sách active/obsolete được so như tập đã sắp xếp. Không tự biến kết quả agreement thành trạng thái approved.

Holdout v1 đã khóa SHA-256 trước train mới, seed 914207, 8 chuỗi/29 bước. Tách user, sequence và nhóm trajectory khỏi train/validation. Đây là tập do cùng trợ lý thiết kế mà không xem prediction mới, **chưa được tác giả/người duyệt độc lập xác nhận**. Pilot 12 chuỗi là development set, giữ nguyên gold. Không gọi nó là holdout mới. Sau khi đã xem v1, thay đổi model tiếp theo cần holdout v2; không sửa v1 để tăng điểm.

Để duyệt mapping MASSIVE: đọc `inspection.json`, xem mẫu của từng intent, sửa rationale nếu cần, ghi danh tính reviewer và `review_status: approved` trong `configs/massive_vi_mapping.json`, review diff rồi chạy lại import. Chỉ người được giao duyệt thực hiện bước này; agent không tự ghi đã duyệt.
