# Tuần 4 — bằng chứng runtime và Web

Ngày2026-10-04; giờ trong JSON là UTC, screenshots hiển thị Asia/Saigon.
`runtime.json`: HTTP thật qua Gateway mới → FastAPI → router/memory/state/Ollama,
read-only SQLite đối soát user giả và stack lỗi riêng. `browser.json`: Chromium
thật → Web/Gateway; RT-01/13, xác nhận/hủy, history, lỗi mạng, retry,401 và390px.
`checks.json`: kết quả lệnh thực, không suy ra CI từ local checks.

Ảnh crop giao diện, không có form password/token/tài khoản người thật:

- `pending.png`: đề xuất và hai nút xác nhận/hủy.
- `network-retry.png`: phản hồi success mất trên mạng sau ghi thật; UI giữ draft.
- `xss-memory.png`: payload HTML chỉ hiển thị dạng text trong memory cards.
- `mobile.png`: Web390px sau khi sidebar đóng/animation settled.

Source local delivery output được giữ ở runtime, chỉ copy artifact đã kiểm tra.
Không copy log process/auth headers/DB hoặc model. Mỗi script tạo user mới; tuyệt
đối không sử dụng kết quả này để gán điểm nội dung/human review cho SFT LLM.
RT-10 dùng URL offline riêng, không stop Ollama; RT-16 foreign port owner không bị
startup kill. Các isolated child processes đã được thu hồi; base/router gốc giữ nguyên.

Xem [báo cáo](../../WEEK4_COMPLETION_REPORT.md) cho root cause, giới hạn và Git/CI.
