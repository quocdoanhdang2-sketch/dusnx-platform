# Báo cáo audit SFT

Manifest SHA-256: `310116ee463e78fff7f0619c4f382eabeb2a7e9cf3060d05d5ec2b508f4710d2`

| Split | Chuỗi | Cặp assistant | Prompt duy nhất | Token min–max–mean |
|---|---:|---:|---:|---:|
| train | 43 | 49 | 49 | 94–187–131.61 |
| validation | 12 | 12 | 12 | 115–145–126.58 |
| test | 6 | 6 | 6 | 101–142–123.33 |

- Trùng prompt chính xác: 0.
- Ngưỡng near-duplicate: 0.82; tương đồng cross-split lớn nhất: 0.6731.
- Near-duplicate trong cùng split: 2; các cặp cùng chuỗi nhiều lượt được giữ để học tiếp nối.
- Validator đã kiểm tra tiếng Việt, required fact có trong ngữ cảnh trước đó, obsolete/rejected fact không vào completion, future fact không lọt ngược và clarification có câu hỏi.
- Mọi record hiện vẫn `needs_human_review`; báo cáo máy không thay thế duyệt nội dung bởi người.
