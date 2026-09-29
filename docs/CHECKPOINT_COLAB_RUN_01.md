# Checkpoint Colab Run 01 và kiểm chứng nguồn câu trả lời

Cập nhật 2026-09-30. HEAD trước nhiệm vụ: `2a7b159db2a6aac549a863258dcee33f76173517`. Không train lại checkpoint và không chạy model/rule/baseline/scorer trên v3 trong nhiệm vụ này.

## Checkpoint đã xác minh

- File local: `training-results/colab-run-01/extracted/dusnx-router-full-01/router.pt`.
- SHA-256 thực đo: `56f56e6d61afc264fb02d690d2872fb3ac5db9749a659c8493fd9d99eab7e7b1`.
- Metadata checkpoint được /health trả về: source commit `50e1042aa45ca99d17c989817a08a0896f7a7935`, best epoch 6, best validation mean macro-F1 `0.8061977767812536`, 3814 train windows / 157 validation windows. Số window khác số event.
- Metadata lưu Python 3.13.15, PyTorch 2.11.0+cu128, Tesla T4. Đây là thông tin artifact Colab được người dùng cung cấp; không phải một phiên train mới do agent chạy trong nhiệm vụ này.
- Train được báo cáo: 371 chuỗi / 4185 event, gồm 3000 event synthetic legacy lặp cao; validation 46 chuỗi / 203 event. Không suy ra độ đa dạng cao từ tổng số dòng.
- API hiện chạy CPU, `checkpoint_loaded=true`, `runtime_mode=trained_dusnx`; `model_version=checkpoint:router.pt:sha256-56f56e6d61af:config-03b14389ce98`.

Mô hình có recurrent global/platform/task state (160/112/112) và ba đầu intent/agent/action. Memory CRUD, pending confirmation và supersede là code ứng dụng + SQLite, **không phải chức năng học được của checkpoint**. Checkpoint không sinh văn bản, không hiểu ảnh, không chứng minh hiểu lịch sinh hoạt hoặc tính cách toàn diện.

## Nguyên nhân metadata sai ở mốc 2a7b159

`main.chat` lấy `get_active_memories_for_context(..., limit=15)` rồi gán mọi ID vào memory_ids_used. SQL trong memory.py đã lọc đúng owner, project/global và active; scoring chỉ xếp hạng, không loại mọi ứng viên không liên quan. Vì vậy AWS và PostgreSQL đều nằm trong candidates.

Sau đó main gọi generate_response; grounding.memory_answer_with_match chọn một bản ghi và dựng `Theo trí nhớ đang hiệu lực: ...`. Code thay văn bản provider bằng template nhưng giữ provider/model và phần lớn ID cũ. Điều kiện thêm ID nếu chưa có không thể loại ID không dùng. **Câu này là template ứng dụng**, dù đường code cũ có gọi provider trước đó; chỉ provider_used=ollama trong log không tự chứng minh nguồn văn bản.

Luồng mới: xác thực → lấy active scoped candidates → chọn chủ đề → template/clarification không gọi provider, hoặc prompt được chọn → HTTP LLM → response qua HttpClient Gateway. [Hợp đồng API đầy đủ](CHAT_RESPONSE_CONTRACT.md) tách candidate_memory_ids, prompt_memory_ids, memory_ids_used, provider_called và response_source. Web giữ memory_ids_used và thêm nhãn nguồn; không hiển thị template là Ollama.

Không hardcode AWS/GCP/PostgreSQL trong logic chọn. Test dùng công cụ thiết kế và đồ uống; test retry xác nhận sửa đã bắt thêm lỗi tăng state version dù transaction memory đã idempotent. Bản sửa giữ state/event khi retry; không thay SQL transaction nguyên tử.

## Bằng chứng thật qua Gateway

Lệnh đã chạy:

```powershell
python/.venv/Scripts/python.exe scripts/verify_chat_provenance.py --output runtime/chat-provenance-final.json
```

[JSON thực chạy đã lược credentials](evidence/chat-provenance/gateway.json), UTC `2026-09-29T20:47:39.083259+00:00` (03:47 ngày 30/09 giờ Việt Nam), status passed. User thử mới: lưu GCP và PostgreSQL → đề nghị AWS → xác nhận → mở phiên mới. GCP được supersede; hai quyết định còn lại active.

Đặt A = `ff4b518617505285d0772c0afd2f5dd3` (AWS), D = `fbcb59a27ead947387eb409bdfb77d59` (PostgreSQL). Đây là alias đọc báo cáo; file JSON giữ ID thật của dữ liệu thử.

| Câu hỏi | Câu trả lời thực tế | IDs dùng | Source / provider_called |
|---|---|---|---|
| Hạ tầng đám mây được chọn cho dự án là gì? | Theo trí nhớ đang hiệu lực: chúng tôi chọn AWS cho dự án hạ tầng đám mây năm 2026. | [A] | grounded_template / false |
| Cơ sở dữ liệu được chọn là gì? | Theo trí nhớ đang hiệu lực: chúng tôi chọn PostgreSQL làm hệ thống cơ sở dữ liệu chính. | [D] | grounded_template / false |
| Hạ tầng đám mây và cơ sở dữ liệu được chọn là gì? | Hai câu nguyên văn trên, mỗi câu một dòng. | [A,D] | grounded_template / false |
| Quyết định hiện tại của tôi là gì? | Tôi chưa đủ bối cảnh để chọn thông tin phù hợp. Bạn muốn hỏi về quyết định hoặc sở thích cụ thể nào? | [] | clarification / false |

Cả bốn có candidate IDs [A,D] (thứ tự theo score), prompt IDs [], provider_used/model_used/tokens_generated=null. provider_ok=true nghĩa lượt thành công theo trường tương thích cũ, **không nói Ollama đã được gọi**. Không có GCP hoặc dấu '..' trong câu trả lời.

Câu riêng `Viết hai câu về lợi ích của việc đọc sách.` có response_source=llm, provider_called=true, provider_used=ollama, model_used=qwen2.5:0.5b, provider_ok=true, tokens_generated=24, prompt_memory_ids=[], memory_ids_used=[]. Văn bản thực tế:

> 1. Reading can improve your vocabulary and comprehension skills.
> 2. Reading can enhance your critical thinking and analytical abilities.

Đây là bằng chứng gọi generation thật, không chỉ health; model đã trả **tiếng Anh dù yêu cầu hệ thống tiếng Việt**. Không sửa output để làm đẹp báo cáo. Các test transport kiểm tra provider lỗi trả provider_ok=false, thiếu cấu hình không báo called, template không được gọi provider.

## Holdout và review

v1/v2 đã xem để chẩn đoán. V2 mock không đo chất lượng LLM; 23/38 lượt mang nhãn nghiệp vụ bộ nhớ ngoài từ vựng neural router. Điểm hybrid chịu ảnh hưởng lớn từ rules/SQLite; chưa chứng minh recurrent state tốt hơn no-state. Không lấy điểm đã xem làm đánh giá độc lập.

V3 SHA thực đo: `094268aaf47fa5328786846aff46ebe2f271fd05e2633e681fee472adc8e71bd`. [Báo cáo integrity-only](evidence/chat-provenance/v3-integrity.json) xác nhận 311 lượt/20 chuỗi, status labels_locked_not_independently_reviewed, CSV/JSONL blind không có nhãn/notes đã điền. Không parse gold labels, không chạy inference/score. [Hướng dẫn reviewer PowerShell](HOLDOUT_V3_REVIEW_GUIDE.md) có thao tác gửi, nhận, kiểm tra đủ dòng, agreement, phân xử và khóa sau khi con người duyệt thật. Chưa có người thật duyệt và agent chưa gửi file cho ai.

## Giới hạn và vận hành

Chọn memory vẫn là heuristic từ khóa, giới hạn 15 candidates; paraphrase/đồng nghĩa hoặc thông tin thiếu có thể cần hỏi lại. LLM citations chưa được xác minh nên memory_ids_used của LLM để trống; prompt_memory_ids báo inclusion riêng. Không diễn giải demo này thành dự án đã hoàn thiện toàn diện.

Khởi động đúng checkpoint:

```powershell
$env:DUSNX_CHECKPOINT = 'D:\Projects\dusnx-platform\training-results\colab-run-01\extracted\dusnx-router-full-01\router.pt'
$env:DUSNX_DEVICE = 'cpu'
powershell -ExecutionPolicy Bypass -File .\start-local.ps1
```

Kiểm tra toàn repo gồm pytest, Node, Gateway tests/build, local-health, compileall source folders và git diff --check. Tiny training fixtures của test suite không phải train lại checkpoint Colab. Không commit training-results, checkpoint, DB, credential hoặc bài reviewer.

Nghiệm thu Tuần 2 đã chạy lại với hợp đồng mới: [HTTP passed](evidence/chat-provenance/week2-http.json), [Web UI thật passed](evidence/chat-provenance/week2-ui.json). Cả hai kiểm tra recall template và một lượt Ollama generation riêng. Playwright dùng Chromium local; ảnh vẫn ở runtime, report không lưu token hoặc password.
