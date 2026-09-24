# Soạn benchmark độc lập cho DUSN-X

Tài liệu này dành cho benchmark do người viết và review độc lập. Không dùng dữ
liệu train synthetic, fixture test hoặc report dự đoán để chọn câu hay sửa nhãn.

## Schema một dòng JSONL

Mỗi dòng phải khớp `dusnx_core.benchmark.BenchmarkStep` và không có field thừa:

```json
{"case_id":"<unique-step-id>","sequence_id":"<sequence-id>","global_user_id":"<anonymous-benchmark-user>","step":1,"platform":"<web|zalo|powerpoint>","content":"<write the utterance here>","known_feedback_value":0.0,"expected_intent":"<intent>","expected_agent":"<agent>","expected_action":"<action>","category":"<category>","difficulty":"<easy|medium|hard>","source":"<human_authored|ai_generated>","generated_by_ai":false,"notes":"<why the label is correct or ambiguous>"}
```

Đây là placeholder, không phải một ca đã gắn nhãn. `case_id` là duy nhất cho
từng bước; `sequence_id` nhóm các bước và chỉ chứa một `global_user_id`. `step`
bắt đầu từ 1 và liên tục.

## Intent, agent và action

| Intent | Dùng khi | Dễ nhầm với | Agent / action |
|---|---|---|---|
| `chat` | Hỏi đáp hoặc giải thích trực tiếp | `research` nếu thực sự cần nguồn/bằng chứng bên ngoài | `conversation` / `reply` |
| `research` | Tìm, kiểm chứng hoặc đối chiếu thông tin | `summarize` chỉ cô đọng tài liệu đã có | `search_rag` / `search` |
| `summarize` | Nén nội dung đã có mà không thêm kết luận mới | `recommendation` đưa ra lựa chọn | `productivity` / `summarize` |
| `presentation_edit` | Tạo hoặc sửa nội dung/bố cục trình chiếu | Chỉ nhắc từ “slide” không đủ để gắn nhãn này | `productivity` / `edit_slide` |
| `recommendation` | Chọn hoặc đề xuất phương án theo mục tiêu/ràng buộc | `research` nếu chỉ thu thập bằng chứng | `conversation` / `recommend` |
| `followup` | Tiếp nối ngữ cảnh hoặc công việc trước | `chat` nếu câu độc lập, không tham chiếu trước đó | `conversation` / `clarify` |

## Sequence và feedback

Một chuỗi xuyên nền tảng có thể đi `web → zalo → powerpoint`. Giữ nguyên
`sequence_id` và `global_user_id`, tăng `step` lần lượt 1, 2, 3. Evaluator giữ
state riêng cho từng sequence.

`known_feedback_value` tại bước **t** chỉ là feedback đã biết trước khi xử lý
bước **t**, thường phát sinh sau bước **t-1**. Không dùng đánh giá của chính câu
trả lời đang được dự đoán. Bước đầu luôn là `0.0`.

## Quy trình hai người trước khi mở prediction

1. Người A viết câu và khóa expected intent/agent/action cùng notes.
2. Người B review độc lập, giải quyết bất đồng bằng contract ở trên.
3. Chạy validator và lưu checksum của JSONL đã chốt.
4. Chỉ sau đó mới chạy evaluator hoặc mở `report.json`/`errors.json`.
5. Không sửa nhãn chỉ để tăng điểm; mọi sửa nhãn phải có lý do và lịch sử review.

Nếu AI sinh hoặc viết lại câu, bắt buộc dùng `source="ai_generated"` và
`generated_by_ai=true`; không đổi thành `human_authored` sau khi biên tập nhẹ.

Không cần cung cấp dữ liệu cá nhân hay hội thoại riêng tư. Nếu dùng hội thoại
thật, phải có quyền sử dụng, loại bỏ thông tin nhận dạng và tuân thủ chính sách
bảo mật áp dụng cho nguồn dữ liệu đó.

## Validate, chạy và đọc report

```powershell
cd D:\Projects\dusnx-platform
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH="$PWD\python\src"

python -c "from dusnx_core.benchmark import read_benchmark; rows=read_benchmark(r'benchmarks\benchmark_v1.jsonl'); print(f'validated {len(rows)} steps')"

python .\python\scripts\evaluate_benchmark.py `
  --benchmark .\benchmarks\benchmark_v1.jsonl `
  --checkpoint .\artifacts\dusnx_smoke_v2.pt `
  --output-dir .\runtime\benchmark-v1-report `
  --device auto
```

`report.json` chứa model prediction, kết quả sau rule, metric và confusion matrix.
`errors.json` tách lỗi model thuần khỏi lỗi sau rule override. Hai file CSV dùng
hàng là expected intent và cột là predicted intent. Kiểm tra
`missing_expected_classes` trước khi diễn giải macro-F1.
