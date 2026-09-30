# Tuần 3: SFT LLM tiếng Việt riêng với router

## Trạng thái bàn giao

Pipeline này fine-tune **Qwen2.5-0.5B-Instruct bằng LoRA**, không train LLM từ đầu và không thay `router.pt`. GPU Colab, adapter thật, merge/GGUF thật và so sánh candidate vẫn cần người dùng chạy. Smoke dùng Qwen ngẫu nhiên rất nhỏ trên CPU chỉ kiểm chứng API, loss mask, update LoRA, checkpoint và resume. Không có điểm chất lượng candidate để công bố.

[Smoke CPU đã chạy đạt](evidence/llm-sft/cpu-smoke.json) bằng `python python/scripts/llm_pipeline_smoke.py --output runtime/llm-smoke-verified` trong venv riêng: weights sau resume khớp train liền (rtol1e-5/atol1e-7), loss không chứa user/system, LoRA thực sự cập nhật, export smoke bị từ chối. `pip check` không có dependency hỏng. Python166/Web11/Gateway7/local-health6 tests đạt; build .NET không warning/error. Đây là kiểm thử pipeline trên Windows CPU, chưa phải chạy Colab GPU.

Base Ollama vẫn là `qwen2.5:0.5b`. Máy kiểm tra có Ollama **0.34.4**. Router Colab đang dùng giữ nguyên SHA-256 `56f56e6d61afc264fb02d690d2872fb3ac5db9749a659c8493fd9d99eab7e7b1`. Không đổi checkpoint router khi chọn LLM.

Bằng chứng HTTP thật trên instance kiểm thử riêng: [Gateway 8180 → FastAPI 8100 → Ollama](evidence/llm-sft/gateway-development-smoke.json) trả base `response_source=llm`, model đúng, 43 token do API báo, khoảng 9.42 giây; candidate chưa tồn tại nên lỗi provider, không có điểm so sánh. [Regression sản phẩm](evidence/llm-sft/product-regression.json) đạt logic memory/provenance nhưng câu sinh về đọc sách của base **bằng tiếng Anh** dù user hỏi tiếng Việt. Không gọi lần chạy này là đạt chất lượng tiếng Việt. Các prompt trên là development smoke, không dùng tập test đã khóa; dịch vụ chính 8080/8000 không bị đổi.

## Nguồn, revision và dữ liệu

Base [Qwen model card](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct/tree/7ae557604adf67be50417f59c2c2f167def9a775): revision `7ae557604adf67be50417f59c2c2f167def9a775`, Apache-2.0, truy cập công khai. Export giữ LICENSE và ghi nhận thay đổi bằng LoRA. Ollama base là bản phân phối/quantization của cùng họ; không giả định digest Ollama đồng nhất byte với HF.

| Split | Chuỗi | Cặp assistant | Prompt duy nhất | Trùng chính xác |
|---|---:|---:|---:|---:|
| Train | 20 | 24 | 24 | 0% |
| Validation | 5 | 5 | 5 | 0% |
| Test nháp | 6 | 6 | 6 | 0% |

31 nhóm kịch bản được soạn riêng, một nguồn `synthetic_designed`, revision `llm-authored-v1`, nội dung giả dành cho sử dụng CC0-1.0. Không phải hội thoại người dùng thật. Độ dài chuỗi theo ký tự: train 243–556, validation 290–401, test 281–421; token length được kiểm tra bằng tokenizer khi train, quá dài thì báo lỗi thay vì cắt mất đáp án. Số lượng này nhỏ, chỉ phù hợp pilot; không bơm thêm bằng thay tên. Tách ID/sequence/user/family và mọi prefix prompt dùng train; kiểm tra trùng chính xác không chứng minh hết trùng ngữ nghĩa. Cần người duyệt tình huống và cách diễn đạt.

Không tải thêm dataset ngoài cho SFT. CSConDa cần quyền gated, MASSIVE chỉ có intent và mapping còn pending, SGD chỉ tham khảo cấu trúc: **đều không nhập SFT**. Chi tiết nguồn cũ ở [DATA_SOURCES.md](DATA_SOURCES.md). Không đọc holdout v3, gold, blind/reviewer package hoặc output v3 để xây/tune/evaluate pipeline này. V1/v2 cũng không dùng làm dữ liệu SFT hay kiểm định độc lập.

**Tập test hiện do AI soạn, chưa đáp ứng yêu cầu do người viết.** Nó được khóa byte bằng manifest trước smoke, nhưng chưa được duyệt độc lập. Full train cố ý yêu cầu human attestation thật; agent không ký thay. Người viết cần tạo 6–12 chuỗi mới trong `test.jsonl`, giữ schema, dùng `source=human_designed`, nguồn/revision riêng, thông tin giả và quyền CC0. Một người khác duyệt trước khi xem prediction. Không chỉ đổi metadata của bản AI để giả làm người viết.

## Duyệt và khóa trước full train

1. Đọc từng hội thoại train/validation; xác minh assistant chỉ dùng lượt trước, phân biệt hiện hành/đề xuất/đã bị thay thế, không tự nhận đã lưu. Sửa nội dung sai rồi đổi `review_status` thành `human_reviewed` khi thực sự đã duyệt.
2. Người thật viết test mới tách câu chữ, câu chuyện, sequence/user/family khỏi train/validation; đặt reference trước khi xem output. Reviewer duyệt tính đúng tiếng Việt, grounded, clarification, không dùng obsolete và hoàn thành yêu cầu. Ghi tác giả, reviewer bằng định danh công việc không nhạy cảm.
3. Khóa **trước train và prediction**, từ project root:

```powershell
$env:PYTHONPATH='python/src'
python python/scripts/lock_llm_data.py --human-author AUTHOR_ID --reviewer REVIEWER_ID --attest-authored-reviewed-before-predictions
python python/scripts/prepare_llm_data.py --output runtime/llm-audit
```

Lệnh đầu chỉ dành cho người xác nhận thật; kiểm tra schema/split trước khi ghi SHA và attestation. Lưu thay đổi dữ liệu/manifest vào commit riêng để Colab checkout đúng SHA. Không chọn hyperparameter theo test. Nếu sửa dữ liệu sau train thì run cũ không còn được so sánh với bộ mới như test đã khóa.

## Bấm trên Colab

1. Mở [notebook](../notebooks/finetune_llm_colab.ipynb), chọn **Open in Colab** qua GitHub hoặc vào Colab → File → Open notebook → GitHub → dán URL repo và chọn `notebooks/finetune_llm_colab.ipynb`.
2. **File → Save a copy in Drive** chỉ lưu notebook; không cần mount Drive cho train. **Runtime → Change runtime type → T4 GPU → Save**. Không có GPU vẫn chạy smoke CPU được, full train báo lỗi rõ.
3. Ô đầu: đặt `REPO_REVISION` thành SHA commit đã duyệt dữ liệu. `main` chỉ là mặc định tiện mở, được resolve/in ra SHA; run manifest luôn ghi SHA thực. Không dùng token trong notebook.
4. Chạy ô cài pinned packages trong venv riêng `/content/dusnx-llm-env`, rồi kiểm tra Python/PyTorch/GPU thật qua interpreter đó. Python 3.11–3.13, torch 2.8.0, Transformers 4.56.2, TRL 0.23.1, PEFT 0.17.1. Kernel Colab giữ thư viện download; môi trường train không dùng torchvision/torchaudio có sẵn. Không khẳng định bộ này đã chạy GPU Colab chỉ vì smoke CPU đạt.
5. Chạy audit và đọc `/content/llm-audit/audit.json`, `human_review_sample.json`. Smoke CPU không tải HF model; kiểm tra hai epoch qua save/resume. Không gọi loss smoke là chất lượng base.
6. Sau duyệt/khóa, bật `RUN_FULL=True`. Chạy chặng epoch 1. Tải **`dusnx-llm-run.zip` và `.zip.sha256`** ngay, kiểm tra trong Downloads.
7. Chạy ô `NEXT_EPOCH=2`, tải ZIP/SHA. Đổi thành 3 rồi chạy và tải lần nữa. Giữ backup trước đó. Mỗi epoch cũng tạo `*-step-N.zip`; `/content` mất khi runtime ngắt, file chưa tải không được bảo toàn. Drive mount là tùy chọn sau mỗi chặng.
8. Nếu ngắt: runtime mới checkout **cùng commit**, cài **cùng versions**, upload ZIP + SHA, bật `RESTORE=True`, giải nén vào RUN trống. Bật RUN_FULL rồi chạy ô NEXT_EPOCH còn lại, **không chạy ô train chặng 1**. Resume giữ optimizer/scheduler/RNG và từ chối config/data/base/library/code đổi.
9. Sau `training_complete`, bật `RUN_EXPORT=True`; merge CPU đúng base revision và convert F16 GGUF. Tải `dusnx-llm-export.zip` + SHA. Tùy chọn `RUN_HF_EVAL=True` sinh cùng prompt cho base/adapter, tải comparison ZIP. Không dùng kết quả để quay lại tune test.

Config `configs/llm_sft.yaml`: 3 epochs, LR 1e-4, batch 1, accumulation 8, length 512, r8/alpha16/dropout0.05, seed20260930, validation loss/early stopping patience2. Loss chỉ trên completion assistant; không train user/system. Full train tải **model công khai** theo revision pin, không tải CSConDa/MASSIVE. CPU merge cần vài GB RAM ngoài môi trường; thiếu RAM dừng export và báo lỗi. OOM train: dùng config mới, giảm length chỉ khi mọi sample vẫn vừa, hoặc bật QLoRA và cài `requirements/llm-qlora.txt` (CUDA + bitsandbytes0.47.0); nhánh QLoRA chưa được kiểm chứng GPU ở máy bàn giao. Không âm thầm chuyển cấu hình khi resume.

## Artifact và đưa về Windows

Run ZIP gồm adapter/tokenizer, `training_manifest.json` (config, data SHA, code SHA, seed, versions, mode), `metrics.json` theo bước/epoch, checkpoint đủ resume, file inventory `artifact_manifest.json`. Export ZIP gồm merged safetensors/tokenizer, F16 GGUF, base LICENSE/NOTICE, export/training manifests. HF/Gateway comparison là artifact riêng. Giữ cả run và export ZIP; ZIP export không thay run resume.

Converter [llama.cpp b6500](https://github.com/ggml-org/llama.cpp/tree/a7a98e0fffed794396b3fbad4dcdbbc184963645) pin commit `a7a98e0fffed794396b3fbad4dcdbbc184963645`; dependencies converter trong venv riêng. Dùng [GGUF FROM theo Ollama](https://docs.ollama.com/import), không giả định Qwen hỗ trợ ADAPTER trực tiếp. Hiện chưa có adapter thật để chứng nhận đường export/import end-to-end; lỗi converter phải giữ trạng thái chưa đạt.

F16 candidate và base Ollama lượng tử hóa có thể khác độ chính xác số/độ trễ; so sánh triển khai không tách được tác động riêng của LoRA. HF base/adapter cùng dtype là phép so sánh bổ sung. Không quy mọi chênh lệch GGUF cho fine-tuning.

Ví dụ PowerShell từ project root (đường D chỉ là ví dụ máy người dùng, code dùng đường tương đối):

```powershell
$env:PYTHONPATH='python/src'
$py='python/.venv/Scripts/python.exe'
$sha=(Get-Content 'D:/Downloads/dusnx-llm-export.zip.sha256' -Raw).Trim()
& $py python/scripts/export_llm.py unpack --zip D:/Downloads/dusnx-llm-export.zip --sha256 $sha --output runtime/llm-export
./scripts/import_llm_ollama.ps1 -ArtifactDir runtime/llm-export -Python $py
```

Import script kiểm tra SHA, base revision, GGUF magic, base vẫn installed, tên candidate riêng; từ chối ghi đè candidate đã tồn tại. Lấy chat template từ base Qwen đang cài, thay FROM bằng GGUF, `ollama create dusnx-vi-v1 -f Modelfile.local`, chạy một câu tiếng Việt. Đó là smoke, chưa phải bằng chứng tốt hơn. Base vẫn nguyên để rollback.

## So sánh thật qua Gateway và quyết định chọn model

Khởi động lại **FastAPI và Gateway đã build code mới**, đặt `DUSNX_ENABLE_LLM_EVAL=1`; chỉ thêm allowlist nếu dùng candidate tên khác. Endpoint `/api/v1/llm-evaluation` cần opaque Bearer token đăng nhập, mặc định tắt. Nó đi Gateway → FastAPI → Ollama, không dùng template/retrieval/rules/state, không lưu prompt vào DB. Đây là đánh giá sinh câu trả lời có context được cấp; không thay thế bài test end-to-end retrieval/router của sản phẩm.

```powershell
$env:DUSNX_ENABLE_LLM_EVAL='1'
$env:DUSNX_LLM_EVAL_MODELS='qwen2.5:0.5b,dusnx-vi-v1'
# Restart the existing local services with these env vars, then:
& $py python/scripts/evaluate_llm_pair.py --output runtime/llm-pair-01
```

Token nhập tại prompt ẩn, không truyền qua command line, không ghi output. Cùng context/prompt/seed/temp/num_predict cho cả hai model; thứ tự được tráo theo case. `raw_outputs.json` ghi model thực, LLM provenance, thời gian, lỗi; `summary.json`, `errors.json`, `blind_ratings.csv` không có token. Chỉ đưa CSV cho reviewer, giữ raw arm mapping riêng đến khi chấm xong. Chấm 0/1 cho **đúng tiếng Việt**, **grounded không bịa**, **quyết định hỏi lại thích hợp**, **không dùng obsolete**, **hoàn thành câu trả lời**; chấm 0 khi provider lỗi. `clarification=1` cũng áp dụng khi đủ context và model trả lời thẳng, không hỏi thừa. Ghi reviewer/date/notes, không tự điền là người đã duyệt.

```powershell
& $py python/scripts/evaluate_llm_pair.py --output runtime/llm-pair-01 --ratings runtime/llm-pair-01/blind_ratings.csv --human-test-attestation datasets/llm_sft/human_test_attestation.json
```

Gate được chốt trước: đủ hai output LLM thật mỗi case, test có human attestation, không case/tiêu chí nào giảm so với base; tiếng Việt >=95%; grounded, clarification, no-obsolete đạt100%; các trung bình không thấp hơn base. Tập nhỏ nên không khẳng định superiority thống kê. Ghi cả ca giảm trong `promotion_report.json`. Chưa đủ review, thiếu candidate hoặc fail thì **không promote**.

Sau gate đạt và các regression test sản phẩm đạt, người vận hành mới đặt `DUSNX_OLLAMA_MODEL=dusnx-vi-v1`, restart FastAPI; router path giữ nguyên. Rollback: đặt lại `qwen2.5:0.5b`, restart và kiểm tra `/v1/health`. Script không tự đổi .env. Chạy `scripts/verify_chat_provenance.py` để kiểm tra memory selection/template/LLM riêng; template recall không được tính vào điểm LLM.

## Kiểm tra local / CI

```powershell
$env:PYTHONPATH='python/src;python;.'
python/.venv/Scripts/python.exe -m pytest python/tests -q
node --test web-ui/app.test.js
dotnet build gateway-dotnet/Dusnx.Gateway.csproj -c Release
dotnet run --project gateway-dotnet.tests/Dusnx.Gateway.Tests.csproj -c Release
./scripts/tests/local-health.tests.ps1
git diff --check
```

SFT dùng **venv riêng**, `pip install -r requirements/llm-sft.txt`, rồi `finetune_llm.py --smoke --output runtime/llm-smoke --stop-after-epoch 1`; resume từ `checkpoint-2` để hoàn tất epoch2. CI đặt HF_HUB_OFFLINE và TRANSFORMERS_OFFLINE; không tải pretrained weights hoặc dataset. Package install cần mạng. File weights/GGUF/ZIP/runtime bị ignore, không commit log riêng tư hoặc token.

Lỗi thường gặp: checksum khác → tải lại ZIP, không bỏ kiểm tra; output tồn tại → resume đúng checkpoint hoặc thư mục mới; HTTP404 → bật env và restart đúng code Gateway/FastAPI; HTTP401 → đăng nhập lại và nhập token kín; provider_error → kiểm tra `ollama list` và candidate import; CUDA OOM → config mới/QLoRA có kiểm tra; gated dataset → không cần cho pipeline này. Full train không được thực hiện cho tới khi người dùng chạy notebook trên GPU và cung cấp artifact.
