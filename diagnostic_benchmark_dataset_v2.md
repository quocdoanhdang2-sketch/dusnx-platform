# DUSN-X Diagnostic Benchmark Dataset V2

**Mô tả:** Tập dữ liệu chẩn đoán bổ sung, tập trung vào các intent còn thiếu (`followup`) và các luồng đa nền tảng phức tạp (Web → Zalo → PowerPoint).
**Quy tắc:** Bổ sung dưới dạng tập diagnostic độc lập, KHÔNG ghi đè lên 20 ca đã khóa của version trước.
**Tác giả Query:** AI Generated (Gemini).
**Trạng thái Review:** Đang chờ Reviewer 2 xác nhận (Cột Review hiện đang trống).

**Lưu ý kỹ thuật:**
1. Các giá trị trong cột **Trạng thái (State)** hiện tại đóng vai trò là chuỗi ngữ cảnh giả lập (context text) để kiểm thử khả năng định tuyến (routing) của model dựa trên lịch sử hội thoại, chưa phản ánh việc model đã thực sự kết nối/đọc dữ liệu thực tế.
2. **Ca kiểm thử S05_Diag-2:** Việc gán nhãn `recommendation / conversation / recommend` cho ca này là quyết định được đưa ra **sau** khi đã xem trước kết quả prediction của tập cũ. Do đó, ca này chỉ mang tính chất diagnostic nội bộ, không được dùng làm căn cứ độc lập để chứng minh model đã tự cải thiện.

## Bảng Dữ Liệu Diagnostic

| **Seq_ID** | **Step** | **Platform** | **Trạng thái (State)** | **Câu truy vấn (Query)** | **Source** | **Intent** | **Expected Agent** | **Expected Action** | **Review** |
| **D01** | 1 | `web` | *null* | "Gợi ý cho tôi vài chủ đề hấp dẫn về ứng dụng AI trong quản trị nhân sự để làm workshop." | `ai_generated` | `recommendation` | `conversation` | `recommend` | \[ \] |
| **D01** | 2 | `zalo` | `topic_list` | "Từ danh sách bạn vừa gợi ý trên web, giải thích sâu hơn về đối tượng khán giả của chủ đề số 2 nhé." | `ai_generated` | `followup` | `conversation` | `reply` | \[ \] |
| **D01** | 3 | `powerpoint` | `topic_details` | "Chuyển ý tưởng và giải thích vừa rồi thành một slide mở đầu trong file này, nhớ thêm biểu tượng robot." | `ai_generated` | `presentation_edit` | `productivity` | `edit_slide` | \[ \] |
| **D02** | 1 | `web` | *null* | "Tìm các bài báo gần đây về xu hướng dịch chuyển chuỗi cung ứng khỏi Trung Quốc." | `ai_generated` | `research` | `search_rag` | `search` | \[ \] |
| **D02** | 2 | `web` | `search_results` | "Tóm tắt lại 3 quốc gia được hưởng lợi nhiều nhất từ các bài báo đó." | `ai_generated` | `summarize` | `productivity` | `summarize` | \[ \] |
| **D02** | 3 | `zalo` | `summary_text` | "Tôi chưa hiểu lắm, bạn làm rõ thêm tại sao Việt Nam lại nằm trong top 3 đó được không?" | `ai_generated` | `followup` | `conversation` | `clarify` | \[ \] |
| **D02** | 4 | `powerpoint` | `clarification_text` | "Tạo một biểu đồ cột so sánh lợi thế của 3 quốc gia đó vào slide số 4 dựa trên dữ liệu bạn vừa có." | `ai_generated` | `presentation_edit` | `productivity` | `edit_slide` | \[ \] |
| **D03** | 1 | `zalo` | *null* | "Bạn tra cứu giúp mình log lỗi hệ thống của ngày hôm qua xem có gì bất thường không." | `ai_generated` | `research` | `search_rag` | `search` | \[ \] |
| **D03** | 2 | `zalo` | `error_logs` | "Ý mình là chỉ lọc các lỗi liên quan đến cổng thanh toán (payment gateway) thôi nhé." | `ai_generated` | `followup` | `conversation` | `clarify` | \[ \] |
| **D03** | 3 | `web` | `filtered_logs` | "Hiển thị chi tiết bảng dữ liệu lỗi thanh toán đó ra giao diện web để mình tiện đối chiếu." | `ai_generated` | `followup` | `conversation` | `reply` | \[ \] |
| **S05_Diag** | 1 | `web` | *null* | "Tìm hiểu thêm về công nghệ 'RAG' trong AI." | `ai_generated` | `research` | `search_rag` | `search` | \[ \] |
| **S05_Diag** | 2 | `web` | `rag_info` | "Có khóa học nào ngắn hạn về cái này trên Coursera không, recommend vài cái xem nào." | `ai_generated` | `recommendation` | `conversation` | `recommend` | \[ \] |
