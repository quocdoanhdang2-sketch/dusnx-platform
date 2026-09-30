# Mẫu viết tập test LLM độc lập

Tập test chính thức phải do một người viết sau khi đọc rubric này, rồi được một người khác duyệt **trước khi bất kỳ prediction nào được tạo**. Bản `datasets/llm_sft/test.jsonl` đang có chỉ là nháp AI và phải được thay thế, không được đổi metadata để giả thành dữ liệu người viết.

## Cách viết 6–12 chuỗi

1. Không đọc output của base/candidate, benchmark v3, gold/blind/reviewer v3 hoặc các lỗi prediction cũ khi soạn.
2. Dùng người dùng, dự án và thông tin hoàn toàn giả. Mỗi `user_id`, `sequence_id`, `scenario_family` phải mới và không xuất hiện trong train/validation.
3. Viết tình huống và cách diễn đạt mới, không chỉ thay tên. Phủ ít nhất: trả lời tiếng Việt, thiếu ngữ cảnh phải hỏi, quyết định bị thay thế, đề xuất/lời đồn chưa xác nhận, chuyển phiên và Web → PowerPoint → Web.
4. Với mỗi lượt assistant, chỉ dùng thông tin xuất hiện trước lượt đó. Ghi `required_facts`, `forbidden_facts`, `future_facts` để validator có thể bắt leakage.
5. Đặt `source=human_designed`, `generation_method=human-authored`, `source_revision` là tên phiên bản nội bộ, `license=CC0-1.0`, `review_status=needs_human_review`. Sau khi người thứ hai duyệt từng dòng mới đổi thành `human_reviewed`.
6. Reviewer đánh dấu: đúng tiếng Việt; đúng fact hiện hành; không dùng obsolete/rejected/rumor; hỏi lại khi mơ hồ; không bịa đã lưu/xác nhận; câu trả lời hoàn tất yêu cầu.

## Một dòng JSONL minh họa

Ví dụ dưới đây chỉ minh họa schema và **không được chép vào test thật**:

```json
{"id":"test-human-001","source":"human_designed","source_revision":"human-test-v1","license":"CC0-1.0","generation_method":"human-authored","scenario_family":"human_unique_family_001","sequence_id":"human-seq-001","user_id":"fictional-human-001","split":"test","review_status":"needs_human_review","data_kind":"designed_conversation","messages":[{"role":"system","content":"Bạn là trợ lý DUSN-X. Luôn trả lời bằng tiếng Việt. Bối cảnh giả lập: [mô tả trạng thái hiện hành và thông tin không còn hiệu lực]."},{"role":"user","content":"[câu hỏi mới do người viết]"},{"role":"assistant","content":"[đáp án tham chiếu chỉ dựa trên context trước đó]"}],"quality_contracts":[{"assistant_turn":1,"language":"vi","response_mode":"answer","required_facts":["[fact hiện hành phải có ở context và answer]"],"forbidden_facts":["[fact cũ có ở context nhưng không được có trong answer]"],"future_facts":[]}]}
```

`response_mode` nhận `answer`, `clarify` hoặc `acknowledge`. Với `clarify`, completion phải có dấu hỏi. `future_facts` chỉ dùng khi fact xuất hiện ở lượt user sau nhưng không được phép xuất hiện trong completion hiện tại.

## Duyệt và khóa

Người viết và reviewer lưu định danh công việc không nhạy cảm. Chạy audit bằng tokenizer chính xác, đọc mọi lỗi, rồi mới khóa:

```powershell
$env:PYTHONPATH='python/src'
runtime/llm-venv/Scripts/python.exe python/scripts/prepare_llm_data.py `
  --tokenizer-model Qwen/Qwen2.5-0.5B-Instruct `
  --tokenizer-revision 7ae557604adf67be50417f59c2c2f167def9a775 `
  --output runtime/llm-audit-reviewed
python/.venv/Scripts/python.exe python/scripts/lock_llm_data.py `
  --human-author AUTHOR_ID --reviewer REVIEWER_ID `
  --train-review-receipt runtime/llm-review-train-validation/review_receipt.json `
  --test-review-receipt runtime/llm-review-test/review_receipt.json `
  --attest-authored-reviewed-before-predictions
```

Commit dữ liệu và manifest đã khóa. Dùng SHA commit đó trong notebook Colab. Không chạy script khóa nếu test vẫn là bản AI, reviewer chưa đọc từng dòng hoặc đã xem prediction.
