# LLM v2: việc cần người thật trước training

Kiểm tra trên checkout cloud HEAD `121d946`, ngày 31/10/2026 (Asia/Saigon).
Máy này **không có** `runtime/llm-v2-human-gate-20261005-114208`.
Vì vậy chưa xác minh được `README_NEXT.md`, `gate_status.json`, `review_manifest.json`,
`review.csv`, `review.md` của gói Windows đó. Không coi gói mới xuất dưới đây là bản
duyệt mới nhất hoặc thay thế công việc đã làm trên Windows.

## Số liệu kiểm lại, chỉ train và validation

| Split | Record / cặp assistant | Schema | Hash khớp manifest | Trạng thái |
|---|---:|---|---|---|
| train | 100 / 100 | đạt | có | 100 needs_human_review |
| validation | 24 / 24 | đạt | có | 24 needs_human_review |

`datasets/llm_sft_v2/manifest.json`: locked=false, training_allowed=false,
official_evaluation_allowed=false. Audit train–validation theo code hiện có:
threshold=0.82, max cross-split=0.7782, không có cặp vượt ngưỡng trong hai split này.
Chưa đo token bằng exact tokenizer ở lượt này. Không đọc test_draft/holdout v3,
không đánh giá tương đồng với test, không suy ra gate toàn bộ đã đạt.

## Người dùng cần làm

1. Trên Windows, giữ nguyên gói `runtime/llm-v2-human-gate-20261005-114208` và các sửa đổi
   chưa đồng bộ. Đối chiếu HEAD/hash với checkout này trước khi áp dụng patch; không
   chép đè gói duyệt. Nếu gói Windows đã có review, dùng validator của gói đó và kiểm
   nguồn/hash của nó; chưa thể xác nhận bằng phiên cloud này.
2. Nếu chưa có gói review phù hợp, cloud đã xuất bản **chưa duyệt** tại
   `runtime/roadmap-20261031/train-validation-review/`. Đọc `review.md`,
   giữ nguyên `review_manifest.json` và các cột nguồn trong `review.csv`.
   Mỗi một trong 124 dòng cần người thật điền:
   - `decision`: approve hoặc revise;
   - `reviewer`: định danh công việc không nhạy cảm của người đã đọc mẫu;
   - `reviewed_at`: thời điểm thật, ISO-8601 có timezone;
   - nếu revise: `revised_answer` và `reason` không rỗng;
   - nếu nội dung fact/contract thay đổi: `revised_quality_contract_json` phù hợp.
   Agent không điền những cột này. Chưa có receipt duyệt hợp lệ cho bản mới xuất.
3. **Approve** khi đáp án đúng fact hiện hành, không dùng fact obsolete/rejected/future,
   không bịa đã lưu/cập nhật, hỏi rõ khi thiếu dữ kiện, đúng ngôn ngữ, diễn đạt tự nhiên
   và thực hiện đủ yêu cầu. **Revise** khi một tiêu chí sai; viết đáp án đầy đủ có
   lý do, chỉ dùng prefix trước lượt assistant. Không nâng ngưỡng similarity để né lỗi.
4. Một người thật viết 6–12 chuỗi test mới theo
   [template](LLM_TEST_AUTHORING_TEMPLATE.md), không xem prediction hoặc test nháp bị khóa.
   Người thứ hai duyệt, khác tác giả. Không đổi metadata test AI thành human-authored.
5. Sau khi review xong, dùng pipeline `python/scripts/review_llm_data.py` với
   `--data datasets/llm_sft_v2`, đúng package và nguồn hash. **Chưa chạy apply lúc này**:
   apply ghi dữ liệu; chỉ chạy sau khi xác nhận nguồn và review đầy đủ.
   Chỉ sau khi có test người viết/người thứ hai duyệt mới chạy audit đầy đủ và
   exact tokenizer, khóa bằng script/receipt hiện có theo runbook.
   Lưu ý các lệnh mặc định trong runbook có thể trỏ bộ v1; luôn chỉ rõ `--data`.
   Code apply hiện tại đọc cả train/validation/test.jsonl để audit. Bộ v2 checkout này
   chưa có test.jsonl người viết, vì vậy không apply train/validation riêng rồi coi
   gate đạt; phải chuẩn bị test người viết và review theo đúng thứ tự trước khi apply.
6. Bộ dữ liệu/test, receipt, attestation và manifest phải hợp lệ trước training hoặc
   prediction test. Khi thay đổi dữ liệu sau export phải xuất/duyệt lại đúng nguồn.

## Giai đoạn 2 hiện tại

CHƯA TRAINING, CHƯA PREDICTION TEST, CHƯA MỞ HOLDOUT, CHƯA PROMOTE.
Không có GPU/Ollama/router checkpoint production trong instance cloud này. Không tạo
pipeline mới hoặc artifact candidate. Giữ base `qwen2.5:0.5b` theo cấu hình hiện có.
Đọc [runbook training](WEEK3_LLM_TRAINING.md) sau khi gate thực sự đạt; số liệu lịch sử
v1 trong tài liệu đó không thay thế gate v2. Dùng output path mới, pin code/data/base
revision, checksum artifact; đánh giá theo nhóm và independent review trước đề xuất promote.

## Precheck chỉ đọc trên Windows hoặc cloud

Repo có `scripts/check_llm_v2_review.py`, chạy bằng Python 3.11+ chuẩn, không cần cài torch.
Không fetch/pull/apply, không sửa CSV/manifest, không mở test/holdout. Nó kiểm các cột
nguồn với đúng train/validation, hash lúc export, đủ 124 khóa dòng và trường duyệt.
Không xuất nội dung mẫu, tên reviewer hoặc thời điểm duyệt trong JSON tổng hợp.

```powershell
Set-Location D:\Projects\dusnx-platform
git status --short
git branch --show-current
git rev-parse HEAD
py -3 scripts/check_llm_v2_review.py --repo . `
  --package runtime/llm-v2-human-gate-20261005-114208 `
  --data datasets/llm_sft_v2
```

Không chép gói cloud đè gói trên Windows. Precheck hỗ trợ manifest review schema 1,
review_type=train_validation, splits=train/validation; schema khác được báo chưa hỗ trợ,
không tự suy ra đã duyệt. `cached_origin_main` là ref Git local, không phải phép đọc live
GitHub. `--expected-main` mặc định là merge `b8c0a71`, có thể chỉ rõ SHA cần đối chiếu.

Exit 2 nghĩa là thiếu gói/dữ liệu/dòng duyệt hoặc lỗi cần xử lý; đây là kết quả gate
đang chặn, không phải công cụ tự sửa. Exit 0 chỉ nghĩa `STRUCTURALLY_COMPLETE_ONLY`:
đủ cấu trúc không chứng minh reviewer là người thật, nội dung sửa đã đúng nghĩa, test
độc lập/receipt/attestation hợp lệ hoặc được phép training. Công cụ luôn trả
`training_authorized_by_this_check=false` và `human_authenticity_verified=false`.
Vẫn cần validators/pipeline hiện có và người thật chịu trách nhiệm duyệt.

Harness chỉ dùng fixture tổng hợp:

```powershell
py -3 -m unittest discover -s scripts/tests -p test_llm_v2_review_precheck.py -v
```

Workflow `review-precheck.yml` chỉ chạy harness này trên Linux/Windows, không cài
model, không training/evaluation hoặc mở test dữ liệu thật. Kết quả Windows chỉ được
coi đã xác minh khi job đó thực sự hoàn tất; không suy ra từ lần chạy Linux local.
