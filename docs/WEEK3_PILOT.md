# Tuần 3 — pilot hội thoại có thể chạy lại

## Tiếp quản trạng thái trên đĩa

HEAD ban đầu: `84312337604e2fdda039f6ed6f4ca6d66fe7e50c` (`main`). Sáu file đã
được sửa nhưng chưa commit: README, WEEK2_ACCEPTANCE, main.py, provider.py,
test_week2_acceptance.py và verify_real_ollama_week2.py. Bản nháp chưa theo dõi:
`python/scripts/evaluate_personalization.py`, `data/evaluation/week3_independent_eval.json`,
cùng các database/WAL. Các file `benchmarks/benchmark_v1/v2_*` và fixture routing
đã nằm trong HEAD; không xóa hoặc thay bằng bộ mới.

Phần đã có: HTTP qua Gateway, metadata provider, bảo toàn nội dung khi đổi quyết
định, 10 chuỗi personalization dạng JSON và runner ba chế độ. Phần còn dở/lỗi:
runner gọi biến `app` chưa định nghĩa, baseline A không gọi LLM, recall sai vì
tìm lại các từ vốn đang thiếu trong cùng câu trả lời, nhãn `target_query` lọt
vào nhánh dự đoán baseline, nguồn routing không biết bị gán thành model, agent/action
chưa chấm, lịch sử bị bỏ khỏi prompt, số từ mock bị báo thành token, báo cáo UI
chưa có bằng chứng đối chiếu. Những lỗi này đã được sửa.

Bản JSON nháp đã chuyển vào **một** nguồn chính:
`benchmarks/week3_personalization_pilot.jsonl`, thêm đổi chủ đề và sửa sở thích.
Bản gốc không mất: giữ cục bộ tại `runtime/takeover/`; runner cũ cũng được sao lưu
tại đó. Không commit dữ liệu xác thực, DB/WAL, server logs hoặc checkpoint.

## Schema và nguồn nhãn

36 dòng, 12 chuỗi tiếng Việt. `case_id` là ID duy nhất của **bước** (giữ quy ước
benchmark_v1), `sequence_id` là ID ca hội thoại, `step` bắt đầu từ 1.

| Nhóm | Trường bắt buộc |
|---|---|
| Định danh/thời gian | `case_id`, `sequence_id`, `step`, `session_id`, `platform` |
| Đầu vào | `user_message`, `project_id` (có thể null), `event_type`, `known_feedback_value` |
| Ngữ cảnh đã xảy ra | `prior_event_ids`: danh sách chính xác ID các bước trước trong cùng chuỗi |
| Routing gold | `expected_intent`, `expected_agent`, `expected_next_action` (schema cho phép null nếu chưa gán) |
| Nội dung gold | `target_query`, `gold_active_facts`, `gold_obsolete_facts`, `requires_clarification`, `expected_keywords`, `forbidden_keywords` |
| Nguồn/duyệt | `category`, `label_source`, `review_status`, `reviewer` |

Validator từ chối thiếu trường, extra fields, ID trùng, nhãn ngoài tập hợp,
chuỗi đảo thứ tự/nhảy bước, reference tương lai, feedback không quan sát được và
khai duyệt độc lập không có reviewer. Pilot này không có feedback quan sát nên
`known_feedback_value=0` cho mọi bước. Ngữ cảnh/memory được tạo bằng replay các
bước trước, không lấy từ `gold_active_facts`. `prediction_input()` dùng allowlist;
label, target_query và metadata duyệt không vào adapter.

**Nhãn chưa được duyệt độc lập.** `label_source=ai_authored_takeover`; không giữ
tuyên bố “con người biên soạn” của bản nháp vì không có bằng chứng. Dữ liệu không
lấy từ generator synthetic. Test kiểm tra không khớp cả template khi thay `{topic}`
bằng wildcard và loader train từ chối record benchmark. Đối chiếu local 30.000
record `data/synthetic_30k_v2.jsonl`: không có câu trùng sau casefold/strip;
SHA-256 dataset train `05dcda691ba5a94a9052022e5bac93ae4426305ae0069f345d2159e02055df2c`.
Điều này không chứng minh độc lập ngữ nghĩa hay tính đại diện; nhóm triển khai đã
xem pilot nên đây không còn là holdout mù.

Quy tắc gán routing: câu hỏi trực tiếp về thông tin đã lưu là `chat/conversation/reply`;
xin gợi ý món ăn là `recommendation/conversation/recommend`; event PowerPoint
chỉ báo đang trình chiếu, không yêu cầu sửa slide, nên gold là `chat/conversation/reply`.
Luồng nhớ/sửa/xác nhận dùng nhãn API tương ứng. Nhãn routing còn thiếu của bản
nháp đã được hoàn thiện theo quy tắc này trước lượt chạy cuối; không đổi gold
để làm khớp dự đoán model. Reviewer cần xem lại chính các quy ước này.

## Ba chế độ và cách đo

- `baseline_a`: cùng Ollama, có lịch sử trong phiên, không có memory xuyên phiên.
- `baseline_b`: cùng Ollama/lịch sử phiên, append-only các chỉ dẫn nhớ/đổi đã gặp;
  không xác nhận, supersede, lọc project hoặc retrieval. Cả hai baseline dùng
  lexical routing chung (`match_explicit_route`, fallback chat), không dùng checkpoint.
- `dusnx`: endpoint thực `/v1/chat` và `/v1/me/events` của ứng dụng qua TestClient,
  tài khoản mới mỗi chuỗi, DB scratch mới mỗi run, checkpoint/state động thật,
  retrieval và luật xác nhận thật. PowerPoint là event HTTP mô phỏng, không phải Office.

Đây là so sánh **hệ thống**, không phải ablation chỉ thay memory: khác cả policy,
retrieval và routing. Không suy ra 83% là công lao của checkpoint học được.
TestClient trong benchmark không chứng minh mạng/Gateway; bằng chứng đó ở Tuần 2.

`predictions.jsonl` có input đã lọc, prediction từng bước, raw `model_prediction`
trước business-rule override, nguồn route, provider status, reply, memory thực dùng
và memory active. `cases.json` nhóm theo chuỗi, `errors.json` giữ mọi bước sai.
Provider lỗi không thành câu trả lời đạt; kết quả các bước đã chạy vẫn được lưu.
`summary.json` ghi mẫu số từng metric, hash benchmark/checkpoint và runtime mode.

Chấm literal trên **câu trả lời**, không lấy memory ID/content truy hồi làm bằng
chứng đã trả lời đúng. Chỉ chấm recall/final ở 12 lượt target; chỉ chấm recall ở
10 lượt có gold facts và excluded facts ở 6 lượt có gold bị loại. Null là không
áp dụng, không được tính đạt. Clarification chấm trên 8 lượt cần hỏi/xác nhận,
bao gồm thiếu ngữ cảnh, ambiguity và yêu cầu đổi; đó không phải 8 ca thiếu ngữ cảnh.
Intent, agent, action được chấm riêng trên cả 36 bước.

Tên legacy `gold_obsolete_facts`/`obsolete_elimination` còn bao gồm giá trị bị từ
chối, mâu thuẫn và ngoài project, ngoài các giá trị thực sự đã supersede. Khi đọc
chỉ số cần giữ phân biệt này. Phép chấm bảo thủ: kể cả nhắc giá trị cũ để phủ định
cũng bị đánh trượt. Tương đương ngữ nghĩa như “màu tối”/“Dark Mode” có thể bị trượt.
Reviewer cần đánh giá câu trả lời thực, không chỉ đọc điểm.

## Kết quả thực chạy cuối

Kết thúc 2026-09-28 **16:12:48 UTC**, Ollama `qwen2.5:0.5b`, CPU cho checkpoint,
Ollama temperature 0.3, num_predict 256, không cố định seed. Chạy lại có thể thay
đổi câu trả lời; không có khoảng tin cậy từ pilot nhỏ này. Không có provider failure.

Benchmark SHA-256: `2137961651d36f0831013c0b2b749f41fcb252ffd96acb12c29d5c6336e179e1`.
Checkpoint SHA-256: `c1e898a0e4830f3b871026c689fa5376b776eeb015efea577d0d7008f4ba7512`.

| Metric (đạt / mẫu số) | Không memory | Memory tĩnh | DUSN-X |
|---|---:|---:|---:|
| Thông tin hiện hành trong câu trả lời | 4/10 | 6/10 | 10/10 |
| Không nhắc thông tin bị loại | 2/6 | 2/6 | 4/6 |
| Hỏi lại / xác nhận khi cần | 3/8 | 1/8 | 8/8 |
| Intent | 11/36 | 11/36 | 31/36 |
| Agent | 13/36 | 13/36 | 36/36 |
| Action | 11/36 | 11/36 | 31/36 |
| Câu trả lời cuối | **4/12 (33,3%)** | **4/12 (33,3%)** | **10/12 (83,3%)** |

Bằng chứng không nhạy cảm: [evidence/week3](evidence/week3/), đủ 108 predictions
cho cùng 36 bước × 3 chế độ. Bản runtime gốc ở `runtime/week3-ollama-final/`.
Lượt đầu ở `runtime/week3-ollama-run1/` được giữ nguyên: 4/12, 3/12, 9/12 về câu
trả lời cuối; lượt đầu chưa có đủ gold routing. Không chọn lọc câu trả lời tốt
giữa hai lượt. Mock đã chạy ở `runtime/week3-mock-final/` để kiểm pipeline,
không dùng làm chất lượng LLM.

## DUSN-X thất bại và phần model/luật

Hai ca sai câu trả lời cuối:

- `case_04_contradictory_info-02`: nhắc cả Microservices và Monolith như các quyết
  định đã nhớ, mặc dù Monolith chỉ có trong câu hỏi mâu thuẫn. DB không tạo memory
  Monolith; đây là lỗi câu trả lời sinh ra.
- `case_09_multi_step_override_chain-06`: nhắc GCP sau khi Azure đã active.
  Trace memory active chỉ có Azure; lịch sử phiên vẫn chứa quyết định cũ và Ollama
  sinh câu trả lời sai. Không xóa lịch sử để che lỗi benchmark.

Năm bước sai intent/action: `case_02...-04`, `case_03...-04`, `case_04...-02`,
`case_08...-02`, `case_09...-06` (ID đầy đủ trong errors.json). Hai câu trả lời
MongoDB/Python vẫn đúng nhưng routing lần lượt thành recommendation/followup.
PowerPoint được route thành edit dù event chỉ báo trình chiếu.

Routing cuối: **26 bước do luật, 10 bước do model**. Raw checkpoint route đúng
**6/11** bước có gold thuộc vocabulary core (các intent nghiệp vụ như memory_create
không thuộc đầu ra model, không ép chấm model vào chúng). Hai baseline không có
raw checkpoint score (0 bước được chấm, không phải 0% model). Ollama là model
sinh văn bản riêng, không phải checkpoint DUSN-X tự train.

Bộ routing pilot đã có cũng được chạy riêng, không gộp vào bảng trên:
`evaluate_benchmark.py --benchmark benchmarks/benchmark_v1_ai_pilot.jsonl ...`:
24 bước/20 chuỗi, macro-F1 intent toàn lớp **0.2827635** raw model và **0.2910053**
sau rule override. Báo cáo cục bộ `runtime/routing-pilot-final/`.

## Lệnh và kiểm tra

Từ root, activate virtualenv rồi đặt `PYTHONPATH=python/src;python;.;scripts`
trên Windows (`:` thay `;` trên Linux):

```powershell
python python/scripts/evaluate_personalization.py --validate-only
python python/scripts/evaluate_personalization.py --provider ollama --device cpu --output-dir runtime/week3-ollama-final
python python/scripts/evaluate_personalization.py --provider mock --device cpu --output-dir runtime/week3-mock-final
python python/scripts/evaluate_benchmark.py --benchmark benchmarks/benchmark_v1_ai_pilot.jsonl --checkpoint artifacts/dusnx_smoke_v2.pt --device cpu --output-dir runtime/routing-pilot-final
python -m pytest python/tests -q --tb=short -p no:cacheprovider
node --test web-ui/app.test.js
dotnet build gateway-dotnet/Dusnx.Gateway.csproj -c Release
dotnet run --project gateway-dotnet.tests/Dusnx.Gateway.Tests.csproj -c Release
powershell -ExecutionPolicy Bypass -File scripts/tests/local-health.tests.ps1
git diff --check
```

Thực chạy: Python **97 passed**, Web **10 passed**, .NET build **0 warnings/errors**,
Gateway tests **7/7**, startup health **2/2**, validator pilot **36/12** và cả ba
bộ routing JSONL cũ đều hợp lệ. `git diff --check` sạch. Python/Node ban đầu lỗi
quyền sandbox (thư mục tmp, spawn EPERM); chạy ngoài sandbox đã xác định và xử lý
được, không đổi test để bỏ qua lỗi. Không đòi hỏi GPU cụ thể.

Reviewer còn cần duyệt nhãn độc lập, taxonomy routing, paraphrase/phủ định, mức
độ công bằng baseline và đánh giá thêm dữ liệu chưa từng xem trước khi công bố
chất lượng tổng quát. Pilot này hoàn tất công cụ và bằng chứng, không tuyên bố
đã giải quyết các ca thất bại trên.
