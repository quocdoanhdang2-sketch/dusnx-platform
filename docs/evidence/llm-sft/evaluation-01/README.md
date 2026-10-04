# LLM evaluation 01 — bằng chứng được kiểm tra lại Tuần 4

Nguồn local: `runtime/llm-pair-fresh-gateway-20261001-070413`.
`raw_outputs.json` đã được đọc và kiểm tra trước khi đưa vào Git: văn bản từ các
kịch bản giả của bộ test, không có credentials, auth headers, thông tin liên hệ
cá nhân hoặc token. Không copy dataset/test.jsonl hoặc blind rating prompts.
`run.json` và `summary.json` giữ nguyên byte của lượt cũ, không tái sinh prediction.
Hash output khớp `66fd9c2ce759ff74646bc5402cb9769f8b907265e19299c3e32f16004f741c55`.

Base `qwen2.5:0.5b`: provider thành công8/8. Candidate `dusnx-vi-candidate`:
thành công8/8. Đây là transport success, không phải content accuracy. Automatic
required-fact exact4/8 mỗi model; forbidden-fact8/8 base,7/8 candidate.
Candidate human-test-003 nhắc20:00–23:00, vi phạm automatic forbidden-fact;
ghi nhận regression, không sửa test để che lỗi. Case008 cả hai trả tiếng Anh.
Case007 có lời nhận đã lưu; heuristic không đo tiêu chí này (mẫu số0), không tính đạt.

Người dùng cung cấp kết quả AI provisional: candidate final-answer4/8, base3/8,
grounded regression human-test-003. **Chưa tìm thấy** `DUSNX_AI_REVIEW_COMPLETE.zip`
hoặc file review gốc trong repo và Downloads đã kiểm tra. Vì vậy không tạo file
rating giả hoặc khẳng định đã đọc review ZIP; các con số này chỉ là thông tin bàn giao.
Nếu nhập gói đó sau này, phải giữ `reviewer=codex-ai-review`, AI provisional,
`independent_human_review=false`, kiểm nguồn/hash và không overwrite test.jsonl.

Promotion: **không promote**. Agent không tạo/chỉnh attestation con người và không
chấm thành independent human review. `run.json` vẫn ghi test_review_status pending;
manifest dataset hiện khóa bởi người dùng là dữ liệu riêng, không chứng minh content
ratings của pair đã được người độc lập duyệt. Không dùng8/8 transport hoặc4/8 AI
để tuyên bố candidate vượt base. Sampling temp0/seed20260930/num_predict256.

Artifact export local `runtime/llm-export-retry3`: inventory toàn bộ file đã verify
SHA-256 bằng `verify_file_manifest`; status training_complete, pretrained_instruct_lora_sft,
epoch3, best checkpoint21, Tesla T4, code commit `b95f5426fc1dcd68f95d491967081d2ae018bbda`.
GGUF hash `2b082741bb01e5b4d31752b144d9ab8010f930dcff8537e73455a2f86547225d`.
Không commit weights/GGUF/ZIP. Manifest training cuối là resume vào chặng đã hoàn tất,
`train_loss=0.0`/runtime0.0417s không được dùng làm thống kê huấn luyện đầy đủ.
Router.pt tách riêng, hash giữ56f56e…; Holdout v3 không chạy trong tác vụ.
