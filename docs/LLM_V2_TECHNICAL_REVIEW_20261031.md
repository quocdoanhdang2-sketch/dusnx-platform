# Review kỹ thuật/AI dữ liệu LLM v2 — 31/10/2026

Đây là phân tích AI và validator, **không phải independent human review**. Không tạo
receipt, không điền decision/reviewer/reviewed_at/reason/revised_answer vào CSV.
Không sửa dữ liệu hoặc mở gate training. Chỉ đọc train/validation; không đọc
test_draft, test độc lập, holdout hoặc prediction của chúng.

## Kết quả kiểm lại

Nguồn: `datasets/llm_sft_v2` tại code baseline `b8c0a71`, dữ liệu chưa thay đổi.
Pipeline hiện có `read_sft` + `audit` cho **train/validation** đạt schema/hash/split:
100 record train, 24 validation, 124 cặp assistant, tất cả needs_human_review.
Similarity theo thuật toán chính thức: max cross-split 0.7782 dưới ngưỡng 0.82.
Kết quả này chưa bao gồm test và không chứng minh chất lượng nội dung đã đạt.

| Family (bỏ tiền tố split) | Mẫu | Ngôn ngữ output hiện có |
|---|---:|---|
| multi_object_clarification | 11 | chỉ VI |
| false_save | 11 | chỉ EN |
| language_policy | 11 | chỉ EN |
| supersede | 11 | chỉ EN |
| pending_not_final | 10 | chỉ VI |
| cross_platform | 10 | chỉ EN |
| missing_memory | 10 | chỉ VI |
| lost_response_retry | 10 | chỉ EN |
| no_future_fact | 10 | chỉ VI |
| revoked_fact | 10 | chỉ EN |
| user_isolation | 10 | chỉ VI |
| technical_code_switch | 10 | chỉ EN |

Tất cả 124 record chỉ có một lượt assistant. Có 57 đáp án khác nhau; không có
quality contract nào có future_facts khác rỗng. Bilingual hiện trải trên cả bộ,
chưa có cả hai ngôn ngữ trong từng family.

## Các vấn đề cần người duyệt xem xét

1. **Thiếu hội thoại nhiều lượt.** Supersede, pending, retry và cross-platform đều
   được kể lại trong một prompt, không có chuỗi thao tác/thay đổi state thực sự.
   Ví dụ train-003 dùng nhãn old/new cùng tên Memcached, train-005 kể lại Web/PowerPoint
   trong một câu. Cần người viết tạo tình huống nhiều lượt, fact cũ/mới khác nhau,
   xác nhận/từ chối thật trong hội thoại. Không dùng metadata family làm bằng chứng
   hệ thống đã học được hành vi state xuyên nền tảng.
2. **Timeout không đủ chứng minh dịch vụ unavailable.** Train-011, -023…-095 và
   validation-011/-023 trả lời API unavailable sau một timeout. Cần giới hạn kết luận
   vào request không nhận được phản hồi và kết quả chưa xác định; kiểm receipt/state
   trước retry mutation. Có 10 mẫu family này, chưa tự điền revision thay reviewer.
3. **Thu hồi một preference có thể bị khái quát quá mức.** Train-009, -021…-093 và
   validation-009/-021 kết luận không có preference active cho cả account, trong khi
   prompt nêu thu hồi một preference. Người duyệt cần làm rõ closed-world context
   hoặc giới hạn câu trả lời vào preference cụ thể; không suy ra mọi sở thích đều mất.
4. **Retry cần đủ khóa thao tác.** Family lost_response_retry có receipt nhưng chưa
   nêu request ID/session/fingerprint rõ. Bổ sung tình huống receipt của đúng request,
   request khác và timeout chưa rõ kết quả; không dạy luôn bỏ qua mọi lần lưu tiếp theo.
5. **Isolation là bài tập văn bản, chưa là runtime isolation.** Family user_isolation
   tự kể dữ liệu người khác trong prompt. Nó không chứng minh retrieval lọc user/project.
   Giữ acceptance runtime riêng; không lấy điểm SFT làm bằng chứng API đã cô lập account.
6. **Future-fact gate chưa được thử bằng fact ở lượt sau.** Dù family no_future_fact
   nói kế hoạch chưa quyết định, mọi future_facts đều rỗng và không có lượt user tương
   lai. Cần người viết bổ sung prefix/completion có kiểm soát thứ tự thời gian.
7. **Độ đa dạng bị ảnh hưởng bởi wrapper.** Input chứa tiền tố dài, mã TRAIN/VALIDATION
   và biến thể “internal design log”. Đây là dữ liệu tổng hợp, không phải nhật ký người
   thật. Nên xem lại wrapper, cách diễn đạt, ngữ cảnh và split theo scenario độc lập.

Chẩn đoán bổ sung (không thay thuật toán/threshold chính thức): chỉ bỏ phần wrapper
đến `TRAIN-nnn:`/`VALIDATION-nnn:` và so sánh lõi câu user giữa train/validation bằng
near_similarity hiện có: max 0.9695, **196 cặp >=0.82**. Đây là bằng chứng mẫu lõi khá
giống nhau dù full-prompt audit đạt; chưa phải kết quả prediction hay đo chất lượng
model. Không nâng ngưỡng hoặc thay manifest để làm gate pass.

## Phần đã hoàn thiện an toàn

- `scripts/check_llm_v2_review.py`: precheck chỉ đọc, không cần torch; phát hiện ô
  thiếu, revision thiếu reason/answer, timestamp thiếu timezone, khóa trùng, nguồn
  đổi hash và sửa cột nguồn. Hỗ trợ gói train/validation schema 1; schema khác fail closed.
- `scripts/tests/test_llm_v2_review_precheck.py`: 13 harness case dùng fixture tạm,
  có kiểm không thay file, không đọc test/holdout, không lộ nội dung trong lỗi/JSON.
- Workflow riêng `review-precheck.yml`: chỉ chạy harness tổng hợp trên Linux/Windows;
  không kích hoạt pipeline training trong workflow này.
- Gói tải về mới nằm dưới runtime, giữ nguyên CSV chưa duyệt, kèm README_NEXT,
  gate_status máy kiểm, báo cáo kỹ thuật và script. Không chép đè gói Windows cũ.

## Kết luận và cổng kế tiếp

**Chưa đủ căn cứ cho training/evaluation v2.** Con người cần xử lý nội dung/chất
lượng nêu trên, duyệt 124 dòng với nguồn/hash đúng; viết 6–12 test độc lập và người
thứ hai duyệt trước prediction. Sau đó dùng validators/receipt/attestation/lock
của pipeline hiện có. Precheck exit 0 chỉ xác nhận cấu trúc, không chứng nhận đã
có reviewer thật hoặc tự mở gate. Không tạo dữ liệu test “người viết” bằng AI.
