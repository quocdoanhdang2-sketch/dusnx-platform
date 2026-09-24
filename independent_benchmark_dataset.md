# DUSN-X Independent Benchmark Dataset

**Mô tả:** Bộ dữ liệu Benchmark độc lập dành cho dự án DUSN-X. Gồm 23 lượt tương tác được tổ chức thành 7 chuỗi đa nền tảng (multi-step sequences).
**Nguồn dữ liệu:** `ai_generated` (Toàn bộ dữ liệu được AI sinh/mô phỏng, không chứa thông tin cá nhân PII).

**Quy trình duyệt (Dành cho Reviewer 2):**
Vui lòng kiểm tra các cột Nhãn đầu ra (`Intent`, `Expected Agent`, `Expected Action`).
- Đánh dấu `[x]` vào cột **Review** nếu bạn đồng ý với nhãn.
- Ghi chú nhãn mới vào ngay ô đó nếu không đồng ý, **trước khi mở prediction**.

## Quy ước Nhãn Dữ liệu
*   **Platform (Event đầu vào):** `web`, `zalo`, `powerpoint`.
*   **Intent:** `chat`, `research`, `summarize`, `presentation_edit`, `recommendation`, `followup`.

---

## Bảng Dữ Liệu Benchmark

| Seq_ID | Step | Platform | Trạng thái (State) | Câu truy vấn (Query) | Source | Intent (Nhãn) | Expected Agent | Expected Action | Review |
| :--- | :---: | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **S01** | 1 | `web` | *null* | "Tìm giúp tôi các báo cáo mới nhất về thị trường AI tạo sinh tại Việt Nam năm 2026." | `ai_generated` | `research` | `SearchAgent` | `search_web` | [ ] |
| **S01** | 2 | `web` | `search_results` | "Đọc 3 link đầu tiên và tóm tắt lại các thách thức chính của thị trường này." | `ai_generated` | `summarize` | `SummaryAgent` | `extract_key_points` | [ ] |
| **S01** | 3 | `zalo` | `summary_text` | "Gửi đoạn tóm tắt vừa rồi qua tin nhắn Zalo này cho tôi nhé để lát báo cáo sếp." | `ai_generated` | `followup` | `ZaloAgent` | `send_message` | [ ] |
| **S02** | 1 | `zalo` | *null* | "Sắp tới mình phải thuyết trình về chiến lược Marketing quý 3, bạn gợi ý vài cấu trúc slide thuyết phục được không?" | `ai_generated` | `recommendation` | `ConsultAgent` | `provide_recommendation` | [ ] |
| **S02** | 2 | `powerpoint` | `slide_structure` | "Áp dụng cấu trúc số 2 bạn vừa gợi ý vào file hiện tại, đổi tone màu chủ đạo sang xanh dương nhé." | `ai_generated` | `presentation_edit` | `PPTAgent` | `apply_template` | [ ] |
| **S02** | 3 | `powerpoint` | `current_slide` | "Đoạn text ở slide số 4 hơi dài, rút gọn lại thành 3 bullet point cho dễ nhìn." | `ai_generated` | `presentation_edit` | `PPTAgent` | `edit_slide_content` | [ ] |
| **S03** | 1 | `web` | *null* | "Chào buổi sáng, hôm nay hệ thống chạy ổn định chứ?" | `ai_generated` | `chat` | `ChatAgent` | `respond_greeting` | [ ] |
| **S03** | 2 | `web` | *null* | "Tôi đang muốn mua một chiếc laptop mỏng nhẹ cho dân văn phòng, ngân sách tầm 25 triệu đổ lại." | `ai_generated` | `recommendation` | `ConsultAgent` | `recommend_product` | [ ] |
| **S03** | 3 | `web` | `product_list` | "Tìm xem các đại lý lớn ở Hà Nội có đang sẵn hàng con Macbook Air M3 bạn vừa gợi ý không." | `ai_generated` | `research` | `SearchAgent` | `search_local_stock` | [ ] |
| **S04** | 1 | `web` | *null* | "Phân tích đối thủ cạnh tranh của Vinamilk trong mảng sữa hạt giúp tôi với." | `ai_generated` | `research` | `SearchAgent` | `search_web` | [ ] |
| **S04** | 2 | `powerpoint` | `research_data` | "Tạo một slide mới tổng hợp các số liệu thị phần sữa hạt vừa phân tích, thêm một biểu đồ tròn so sánh." | `ai_generated` | `presentation_edit` | `PPTAgent` | `create_chart_slide` | [ ] |
| **S04** | 3 | `powerpoint` | `current_slide` | "Làm cho cái tiêu đề của slide này in đậm và to hơn chút nữa đi." | `ai_generated` | `presentation_edit` | `PPTAgent` | `format_text` | [ ] |
| **S05** | 1 | `zalo` | *null* | "Đọc đoạn tin nhắn dài ngoẵng của sếp ở trên và tóm tắt lại 3 task ưu tiên cần làm ngay hôm nay." | `ai_generated` | `summarize` | `SummaryAgent` | `extract_tasks` | [ ] |
| **S05** | 2 | `web` | `task_list` | "Tìm hiểu thêm về công nghệ 'RAG' mà sếp vừa nhắc tới trong task số 1." | `ai_generated` | `research` | `SearchAgent` | `search_web` | [ ] |
| **S05** | 3 | `web` | `rag_info` | "Có khóa học nào ngắn hạn về cái này trên Coursera không, recommend vài cái xem nào." | `ai_generated` | `recommendation` | `ConsultAgent` | `search_courses` | [ ] |
| **S06** | 1 | `zalo` | *null* | "Khổ thân mình ghê, nãy giờ ngồi chỉnh file báo cáo mãi mà không xong." | `ai_generated` | `chat` | `ChatAgent` | `respond_empathy` | [ ] |
| **S06** | 2 | `powerpoint` | *null* | "Thôi bạn tự động căn chỉnh lại toàn bộ font chữ trong file này về chuẩn Arial size 18 giúp mình nhé." | `ai_generated` | `presentation_edit` | `PPTAgent` | `format_all_slides` | [ ] |
| **S06** | 3 | `powerpoint` | `formatted_ppt` | "Thêm một slide trắng ở cuối cùng ghi mỗi chữ 'Thank You' thôi nha." | `ai_generated` | `presentation_edit` | `PPTAgent` | `create_slide` | [ ] |
| **S07** | 1 | `web` | *null* | "Hãy tìm các số liệu về xu hướng du lịch bền vững của giới trẻ châu Á năm nay." | `ai_generated` | `research` | `SearchAgent` | `search_web` | [ ] |
| **S07** | 2 | `web` | `research_data` | "Được rồi, cô đọng các xu hướng đó lại thành 4 ý chính ngắn gọn nhất có thể." | `ai_generated` | `summarize` | `SummaryAgent` | `generate_summary` | [ ] |
| **S07** | 3 | `powerpoint` | `summary_text` | "Bỏ 4 ý này vào một slide mới, thiết kế layout theo phong cách thiên nhiên xanh mát." | `ai_generated` | `presentation_edit` | `PPTAgent` | `create_slide` | [ ] |
| **S07** | 4 | `powerpoint` | `current_slide` | "Đổi hình nền slide đó sang ảnh một khu rừng nhiệt đới đi cho hợp." | `ai_generated` | `presentation_edit` | `PPTAgent` | `change_background` | [ ] |
| **S07** | 5 | `zalo` | `slide_url` | "Nhắn vào group chat báo cho team biết là mình đã update xong cái slide du lịch bền vững rồi nha." | `ai_generated` | `followup` | `ZaloAgent` | `send_message` | [ ] |
