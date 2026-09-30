# Báo cáo bàn giao Tuần 3: LLM SFT Pipeline, Rà soát Dữ liệu và Kiểm thử

> **Trạng thái:** Toàn bộ phần mã nguồn, dữ liệu phát triển, công cụ review/khóa, kiểm thử tự động, tài liệu và quy trình huấn luyện của Tuần 3 đã **hoàn tất 100% về mặt kỹ thuật**.  
> **Cổng chờ:** Đang chờ con người duyệt dữ liệu thực tế, viết tập test độc lập, chạy huấn luyện LoRA trên Google Colab GPU và chấm điểm candidate qua Gateway.  
> **Tuyên bố trung thực:** Chưa chạy huấn luyện GPU và chưa có model LoRA hoàn chỉnh; model mặc định của hệ thống vẫn là base `qwen2.5:0.5b`, checkpoint router `router.pt` được bảo toàn nguyên vẹn.

---

## 1. Mốc Git và tệp thay đổi

- **Mốc cơ sở (Base commit):** `fd4308264d10ae8e156d498a38f62e6dc98a8d84` trên nhánh `main`.
- **Nguyên tắc:** Giữ vững mọi thay đổi uncommitted đã có trong workspace; không reset, clean hay ghi đè tùy tiện; không đụng đến `router.pt` hay tập holdout v3.

### Danh mục tệp thay đổi và bổ sung:

| STT | Đường dẫn | Trạng thái | Mục đích |
|---|---|---|---|
| 1 | `datasets/llm_sft/train.jsonl` | Modified | Sửa 4 record lỗi (`train-006`, `017`, `020`, `025`) và cập nhật contract |
| 2 | `datasets/llm_sft/manifest.json` | Modified | Cập nhật hash development revision `llm-authored-v2.1` |
| 3 | `python/src/dusnx_core/llm_data.py` | Modified | Thêm regex kiểm tra hash của train/test review receipts trong gate khóa |
| 4 | `python/src/dusnx_core/llm_review.py` | **New** | Module xuất gói duyệt (`export_package`) và nhập duyệt (`apply_package`) chống giả mạo |
| 5 | `python/scripts/review_llm_data.py` | **New** | CLI tiện ích xuất/nhập gói review Markdown + CSV cho người dùng |
| 6 | `python/scripts/lock_llm_data.py` | Modified | Bắt buộc 2 receipt duyệt thật (train+validation và independent test) |
| 7 | `python/scripts/finetune_llm.py` | Modified | Kiểm tra multi-turn completion masking toàn diện; gate khóa trước full train |
| 8 | `python/scripts/llm_pipeline_smoke.py` | Modified | Nhận diện checkpoint resume động theo mẫu `checkpoint-*` |
| 9 | `python/scripts/evaluate_llm_pair.py` | Modified | Đánh giá so sánh song song base và candidate, kiểm tra tự động và tạo blind rating CSV |
| 10 | `python/scripts/evaluate_llm_hf.py` | Modified | Kiểm tra gate trước khi sinh so sánh qua HuggingFace |
| 11 | `python/apps/ai_api/llm_evaluation.py` | Modified | Cập nhật candidate allowlist mặc định `dusnx-vi-candidate` |
| 12 | `python/tests/test_llm_sft.py` | Modified | 33 bài test tự động cho toàn bộ pipeline SFT, data review, receipts và masking |
| 13 | `scripts/import_llm_ollama.ps1` | Modified | Nhận diện candidate `dusnx-vi-candidate`, hỗ trợ fallback tìm file `.gguf` linh hoạt |
| 14 | `notebooks/finetune_llm_colab.ipynb` | Checked | Kiểm tra toàn bộ 20 ô của notebook Colab (SHA checkout, pinned stack, CUDA, checkpoints) |
| 15 | `docs/LLM_TEST_AUTHORING_TEMPLATE.md` | Modified | Cập nhật lệnh khóa dữ liệu chuẩn xác với 2 receipt duyệt thật |
| 16 | `docs/WEEK3_LLM_TRAINING.md` | Modified | Đồng bộ tên candidate `dusnx-vi-candidate` và hướng dẫn review v2.1 |
| 17 | `docs/evidence/llm-sft/data-quality-review-v2.1.md` | **New** | Bảng ghi nhận chi tiết 4 record sửa đổi có căn cứ |
| 18 | `docs/evidence/llm-sft/data-audit-v2.1.md` | **New** | Báo cáo kiểm định tokenizer chính xác và độ tương đồng |
| 19 | `docs/evidence/llm-sft/data-audit-v2.1.json` | **New** | Dữ liệu kiểm định máy chi tiết của development data v2.1 |
| 20 | `README.md` | Modified | Cập nhật hướng dẫn Tuần 3, công cụ review và trạng thái bàn giao |
| 21 | `docs/WEEK3_HANDOFF.md` | **New** | Báo cáo bàn giao tổng kết Tuần 3 |

---

## 2. Thống kê dữ liệu và mã băm SHA-256

- **Bộ dữ liệu:** `datasets/llm_sft` (phiên bản `llm-authored-v2.1`)
- **Base model revision:** `Qwen/Qwen2.5-0.5B-Instruct` tại commit SHA `7ae557604adf67be50417f59c2c2f167def9a775`
- **Max sequence length:** 512 tokens

| Phân vùng (Split) | Chuỗi (Sequences) | Cặp Assistant | Prompt duy nhất | Trùng chính xác | Token min–max–mean | Mã băm SHA-256 |
|---|---:|---:|---:|---:|---:|---|
| **train.jsonl** | 43 | 49 | 49 | 0% | 94 – 187 – 133.02 | `4816a3569d4efe514b3944d0ba6b9b65b9d8362d921890c026dc46149959b813` |
| **validation.jsonl** | 12 | 12 | 12 | 0% | 115 – 145 – 126.58 | `c8bd9c2793b811b1184ef288552d4703defa910c412b13a4f7535c5c791833a9` |
| **test.jsonl** (bản AI nháp) | 6 | 6 | 6 | 0% | 101 – 142 – 123.33 | `424507337625b33112009f8cb58f94e9a3cda81cb348e8cb58800ef906c068ae` |

- **Mã băm Manifest Development:** `8f97323ff91156d9c13b12845fed2585ee3149da76141bd5fbdeabfe7900f40a`
- **Độ tương đồng near-duplicate:** Ngưỡng 0.82; độ tương đồng lớn nhất giữa các split là **0.6731** (đạt tiêu chuẩn cô lập). Hai cặp vượt ngưỡng trong train là các lượt liên tiếp của cùng chuỗi hội thoại nhiều lượt.

---

## 3. Các lỗi nội dung đã sửa trong Development Data

Theo yêu cầu của Phần B, 43 record train và 12 record validation đã được rà soát từng dòng:

| ID | Lỗi phát hiện | Cách sửa | Lý do căn cứ |
|---|---|---|---|
| `train-006` | Đáp án mẫu tự giới hạn yêu cầu "tối đa hai ý" vào "trong cuộc trao đổi này", tự thêm phạm vi mà người dùng không yêu cầu. | Bỏ cụm từ tự thêm; đáp án trả lời: "Mình sẽ trả lời ngắn, tối đa hai ý." Contract siết chặt: `required_facts: ["tối đa hai ý"]`, `forbidden_facts: ["trả lời dài"]`. | Trợ lý bám sát đúng yêu cầu của người dùng; việc lưu sở thích lâu dài thuộc thẩm quyền của ứng dụng. |
| `train-017` | Lời kể của người dùng ("Ứng dụng vừa báo đã xác nhận...") bị nâng thành state có thẩm quyền đã xác nhận. | Đưa quyết định lịch tháng bảy vào system context với provenance rõ ràng "Bối cảnh giả lập do ứng dụng cung cấp: state đã xác nhận lịch phát hành hiện hành là tháng bảy". Người dùng chỉ hỏi: "Nhắc lại lịch phát hành hiện hành." | Phân biệt rõ sự kiện hệ thống đã kiểm chứng với lời kể chưa xác thực trong hội thoại. |
| `train-020` | Bối cảnh "chưa xác nhận lưu" dễ gây hiểu lầm là phủ nhận một thao tác DB thực tế đã chạy thành công trong sản phẩm. | System context ghi rõ: "yêu cầu bên dưới chưa đi qua luồng ghi cơ sở dữ liệu và chưa có kết quả lưu". Đáp án: "Yêu cầu lưu cần được ứng dụng xử lý; mình chưa thể xác nhận đã lưu." | Chỉ dạy LLM từ chối khi thực sự chưa có kết quả ghi nhận từ cơ sở dữ liệu. |
| `train-025` | Người dùng yêu cầu tóm tắt ba rủi ro nhưng context không cung cấp; đáp án cũ tự bịa (trễ tiến độ, vượt ngân sách, thiếu người phụ trách). | Đưa dữ liệu nguồn ba rủi ro vào system context và bổ sung cả ba vào `required_facts` của contract. | Dạy model tuân thủ định dạng ngắn gọn mà không tạo ảo giác (hallucination). |

Toàn bộ 39 record train còn lại và 12 record validation đã được đối chiếu: ngữ cảnh, fact hiện hành/bị hủy/tương lai, trạng thái xác nhận và chất lượng tiếng Việt đều đạt chuẩn.

---

## 4. Kết quả kiểm thử thực tế trên hệ thống (Thực chạy 100%)

Tất cả các bài kiểm tra dưới đây đã **thực sự chạy** trên môi trường máy và đều **PASS**:

1. **Python Full Test Suite:**
   - Lệnh: `pytest python/tests`
   - Kết quả: **180 passed in 37.25s** (Bao gồm core, router, state, memory grounding, provenance, week1 & week2 acceptance).
2. **SFT Unit & Regression Tests:**
   - Lệnh: `pytest python/tests/test_llm_sft.py`
   - Kết quả: **33 passed in 8.82s** (Kiểm tra loss mask, multi-turn assistant boundary, format review package, tamper check, verification gate).
3. **Python Syntax & Bytecode Compilation:**
   - Lệnh: `python -m compileall python/`
   - Kết quả: **PASS** (Không có lỗi cú pháp).
4. **SFT Offline Resume & Training Smoke:**
   - Lệnh: `python python/scripts/llm_pipeline_smoke.py --output runtime/ci-llm`
   - Kết quả: **PASS** (Xác nhận weights giữa chặng ngắt resume và chặng chạy liền trùng khớp 100% qua `torch.testing.assert_close`; multi-turn mask verified; LoRA update verified; xuất GGUF từ smoke bị từ chối chuẩn xác).
5. **Personalization Benchmark Pipeline Smoke:**
   - Lệnh: `python python/scripts/pipeline_smoke.py` và `evaluate_personalization.py --validate-only`
   - Kết quả: **PASS** (36 bước / 12 chuỗi pilot hợp lệ).
6. **Web UI Security & Rendering Tests:**
   - Lệnh: `node --test web-ui/app.test.js`
   - Kết quả: **11 passed in 119ms** (Kiểm tra XSS, an toàn `textContent`, hiển thị nguồn gốc câu trả lời).
7. **.NET Gateway Build & History Tests:**
   - Lệnh: `dotnet build gateway-dotnet/Dusnx.Gateway.csproj -c Release` & `dotnet run --project gateway-dotnet.tests/Dusnx.Gateway.Tests.csproj -c Release`
   - Kết quả: **Build thành công (0 warning, 0 error); 7/7 tests passed**.
8. **PowerShell Local Startup Health Tests:**
   - Lệnh: `./scripts/tests/local-health.tests.ps1`
   - Kết quả: **6/6 passed**.
9. **Git Diff Hygiene:**
   - Lệnh: `git diff --check`
   - Kết quả: **PASS** (Không có lỗi khoảng trắng thừa hay xung đột).

---

## 5. Bảng trạng thái pipeline: Chạy thật vs CPU Smoke vs Chưa chạy

| Thành phần | Trạng thái | Bằng chứng | Ghi chú |
|---|---|---|---|
| Dữ liệu SFT Train & Validation v2.1 | **Đã hoàn thiện code & schema** | `data-audit-v2.1.md`, `test_llm_sft.py` | Sẵn sàng cho người thật duyệt qua CSV |
| Cổng xuất/nhập duyệt (`llm_review.py`) | **Chạy thật 100%** | `test_review_package_round_trip` | Đảm bảo tính toàn vẹn, chống sửa đổi |
| Gate khóa dữ liệu (`lock_llm_data.py`) | **Chạy thật 100%** | `test_lock_command_rejects_*` | Chặn đứng dữ liệu chưa được người thật duyệt |
| Router checkpoint (`router.pt`) | **Chạy thật và bảo toàn** | `artifacts/` hoặc `training-results/` | Giữ nguyên từ Colab Run 01 |
| SFT CPU Smoke (Tiny random model) | **Chạy thật 100%** | `llm_pipeline_smoke.py` passed | Kiểm chứng loss mask, resume, LoRA update |
| Base Ollama LLM (`qwen2.5:0.5b`) | **Chạy thật cục bộ** | Ollama API `:11434` | Sẵn sàng làm đối chứng rollback |
| Huấn luyện LoRA trên GPU Google Colab | **CHƯA CHẠY** | Cần người dùng chạy notebook | Đang chờ con người duyệt dữ liệu & cấp GPU |
| Export GGUF từ weights LoRA thật | **CHƯA CHẠY** | Cần artifact sau Colab GPU | Script `export_llm.py` đã sẵn sàng |
| Import Ollama Candidate (`dusnx-vi-candidate`) | **CHƯA CHẠY** | Cần file `.gguf` thật | Script `import_llm_ollama.ps1` đã sẵn sàng |
| Đánh giá so sánh song song base/candidate | **CHƯA CHẠY** | Cần candidate model thật | Script `evaluate_llm_pair.py` đã sẵn sàng |

---

## 6. Sơ đồ luồng dữ liệu và thực thi (Pipeline Architecture)

```
[43 Train + 12 Validation JSONL]
            │
            ▼
[review_llm_data.py export] ──► runtime/llm-review-train-validation/
                                    ├── review.md (người đọc duyệt)
                                    └── review.csv (điền approve/revise, lý do)
                                                │
[review_llm_data.py apply]  ◄───────────────────┘
            │
            ▼
[test.jsonl (6-12 test mới do NGƯỜI VIẾT)] ──► [review_llm_data.py export (test)]
                                                    │ (người thứ hai duyệt)
                                                    ▼
                                           [review_llm_data.py apply (test)]
            │
            ▼
[prepare_llm_data.py (exact tokenizer Qwen revision pin)]
            │
            ▼
[lock_llm_data.py (chỉ chạy khi có 2 receipt thật từ người duyệt)]
            │
            ▼
Commit Git SHA 40 ký tự ──► Google Colab T4 GPU (notebooks/finetune_llm_colab.ipynb)
                                    │
                                    ├── Epoch 1, 2, 3 (chặn mất kết nối bằng resume)
                                    ├── Tải dusnx-llm-run.zip + .sha256
                                    ├── Merge base + LoRA & convert llama.cpp F16 GGUF
                                    └── Tải dusnx-llm-export.zip + .sha256
                                                │
                                                ▼ (Đưa về máy Windows)
                                    [import_llm_ollama.ps1]
                                                │
                                                ▼
                                    Ollama tạo: dusnx-vi-candidate
                                    (base qwen2.5:0.5b vẫn giữ nguyên)
                                                │
                                                ▼
                                    [evaluate_llm_pair.py] qua Gateway :8080
                                                │
                                                ├── raw_outputs.json (ẩn arm mapping)
                                                └── blind_ratings.csv (người chấm mù 0/1)
                                                            │
                                                            ▼
                                    Promotion Gate: Không hồi quy, >=95% Tiếng Việt,
                                    100% Grounded/No-obsolete/No-false-save
                                                │
                                                ├── ĐẠT: Đổi DUSNX_OLLAMA_MODEL=dusnx-vi-candidate
                                                └── KHÔNG ĐẠT: Giữ nguyên base qwen2.5:0.5b
```

---

## 7. Các cổng còn đóng và hành động của Người dùng

Hiện tại, toàn bộ mã nguồn tự động hóa đã hoàn thành. Người dùng cần thực hiện các thao tác thủ công sau:

### Cổng 1: Duyệt 43 train và 12 validation (61 assistant turns)
1. Mở PowerShell tại thư mục gốc dự án:
   ```powershell
   $py = 'python/.venv/Scripts/python.exe'
   $env:PYTHONPATH = 'python/src;python'
   & $py python/scripts/review_llm_data.py export --kind train-validation --output runtime/llm-review-train-validation
   Start-Process runtime/llm-review-train-validation/review.md
   Start-Process runtime/llm-review-train-validation/review.csv
   ```
2. Đọc `review.md` và điền vào `review.csv`:
   - Cột `decision`: `approve` (hoặc `revise` nếu sửa).
   - Cột `reviewer`: Định danh người duyệt (ví dụ: `reviewer-anh-tuan`).
   - Cột `reviewed_at`: Thời gian chuẩn ISO-8601 có múi giờ (ví dụ: `2026-10-01T10:00:00+07:00`).
   - Nếu `revise`: điền `revised_answer` và `reason`.
3. Nhập kết quả duyệt:
   ```powershell
   & $py python/scripts/review_llm_data.py apply --package runtime/llm-review-train-validation
   ```

### Cổng 2: Soạn 6–12 test MỚI độc lập và duyệt chéo
1. Một người thật viết 6–12 record mới vào `datasets/llm_sft/test.jsonl` theo [LLM_TEST_AUTHORING_TEMPLATE.md](LLM_TEST_AUTHORING_TEMPLATE.md).
2. Xuất gói duyệt test:
   ```powershell
   & $py python/scripts/review_llm_data.py export --kind test --output runtime/llm-review-test `
     --human-author "nguoi-soan-de" --human-authored-at "2026-10-01T09:00:00+07:00"
   ```
3. Người thứ hai (khác người soạn đề) mở `runtime/llm-review-test/review.csv` điền quyết định, sau đó áp dụng:
   ```powershell
   & $py python/scripts/review_llm_data.py apply --package runtime/llm-review-test
   ```

### Cổng 3: Khóa dữ liệu trước khi train
1. Chạy audit và khóa dữ liệu:
   ```powershell
   & runtime/llm-venv/Scripts/python.exe python/scripts/prepare_llm_data.py `
     --tokenizer-model Qwen/Qwen2.5-0.5B-Instruct `
     --tokenizer-revision 7ae557604adf67be50417f59c2c2f167def9a775 `
     --max-length 512 --output runtime/llm-audit-reviewed

   & $py python/scripts/lock_llm_data.py `
     --human-author "nguoi-soan-de" `
     --reviewer "nguoi-duyet-de" `
     --train-review-receipt runtime/llm-review-train-validation/review_receipt.json `
     --test-review-receipt runtime/llm-review-test/review_receipt.json `
     --attest-authored-reviewed-before-predictions
   ```
2. Commit dữ liệu đã khóa lên Git và lấy SHA 40 ký tự.

### Cổng 4: Chạy Colab GPU và đưa Candidate về máy
1. Mở notebook `notebooks/finetune_llm_colab.ipynb` trên Google Colab với GPU T4.
2. Dán SHA commit ở Cổng 3 vào biến `REPO_REVISION`.
3. Bật `RUN_FULL = True`, chạy lần lượt từng epoch, tải về `dusnx-llm-run.zip` và `dusnx-llm-export.zip` kèm file `.sha256`.
4. Giải nén và import vào Ollama trên máy:
   ```powershell
   $sha = (Get-Content "D:/Downloads/dusnx-llm-export.zip.sha256" -Raw).Trim()
   & $py python/scripts/export_llm.py unpack --zip "D:/Downloads/dusnx-llm-export.zip" --sha256 $sha --output runtime/llm-export
   ./scripts/import_llm_ollama.ps1 -ArtifactDir runtime/llm-export -Python $py -Candidate dusnx-vi-candidate
   ```

### Cổng 5: Đánh giá mù song song qua Gateway và quyết định chuyển giao
1. Khởi động hệ thống với cờ đánh giá:
   ```powershell
   $env:DUSNX_ENABLE_LLM_EVAL = '1'
   $env:DUSNX_LLM_EVAL_MODELS = 'qwen2.5:0.5b,dusnx-vi-candidate'
   & $py python/scripts/evaluate_llm_pair.py --output runtime/llm-pair-01
   ```
2. Người thật mở `runtime/llm-pair-01/blind_ratings.csv` chấm điểm 0/1 cho các tiêu chí.
3. Chạy lệnh tổng kết gate:
   ```powershell
   & $py python/scripts/evaluate_llm_pair.py --output runtime/llm-pair-01 --ratings runtime/llm-pair-01/blind_ratings.csv
   ```
4. Nếu kết quả báo `promote: true`: Người vận hành chuyển `DUSNX_OLLAMA_MODEL=dusnx-vi-candidate`.

---

## 8. Định nghĩa hoàn tất Tuần 3 (Definition of Done)

Tuần 3 được coi là hoàn tất chính thức và sẵn sàng chuyển sang Tuần 4 khi và chỉ khi:
1. Gói dữ liệu `train.jsonl` và `validation.jsonl` có chữ ký duyệt thật của con người (`human_reviewed`).
2. Tập `test.jsonl` gồm 6–12 test mới do người viết độc lập và được người thứ hai duyệt mù trước khi sinh kết quả.
3. Manifest có trạng thái `human_attested_locked_before_training`.
4. Checkpoint LoRA và file GGUF được tạo thành công trên Google Colab GPU với GPU thật, có mã SHA xác minh.
5. Model `dusnx-vi-candidate` được nạp vào Ollama và vượt qua Promotion Gate khi đối đầu với `qwen2.5:0.5b` (không hồi quy, đạt tiêu chuẩn tiếng Việt và grounded 100%).
6. Base model `qwen2.5:0.5b` được bảo lưu đầy đủ để sẵn sàng rollback nếu cần.
