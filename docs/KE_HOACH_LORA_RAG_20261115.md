# Kế hoạch LoRA + RAG cho chatbot cá nhân DUSN-X

Ngày lập: 2026-11-15 · Người lập: trợ lý kỹ thuật · Căn cứ: trạng thái thật của repo
`D:\Projects\dusnx-platform` (đọc trực tiếp file, hash, artifact — không dựa vào trí nhớ).

Mục đích: trả lời đúng câu thầy nhận xét ("làm về AI quá, chưa train được gì"), chỉ ra cái gì
đã có, cái gì còn thiếu, và thứ tự bước đi để có 2 app RAG và LoRA chạy được, có số đo.

---

## 0. Kết luận trong 6 dòng

1. Repo **đã train thật**, không phải "chưa train gì": router neural (Colab, `router.pt`,
   sha256 `56f56e6d61af…`) và **LoRA Qwen2.5-0.5B-Instruct v3** (`runtime/sft-run-v3`,
   42 step / 3 epoch, train_loss 1.61, eval_loss 1.26, adapter 4,35 MB, bf16, RTX 3050).
2. Nhưng câu "chưa train được gì" **đúng ở 3 chỗ**: chưa model nào được promote (base vẫn
   trả lời), 181 phiên làm việc thật chưa duyệt được dòng nào, và toàn bộ bằng chứng
   (adapter, quy chế, corpus) đang **untracked** trong git — người ngoài máy này không thấy.
3. Đường ống "lấy quá trình làm việc cho vào LoRA" **đã có code** nhưng **đứt ở cổng duyệt
   tay**: `review_queue.csv` sinh ra bị **sai chuẩn CSV** (ngoặc kép trong JSON không escape),
   nên file không đọc được bằng Excel/pandas/PowerShell — không ai điền được `decision`.
4. Phần "tập trung 1 dữ liệu, 10–20 văn bản" **đã xong**: `datasets/domain_corpus_v1`
   = 16 tài liệu, manifest SHA-256, 20 câu test, index `runtime/domain-rag` 224 chunk.
   Đo được hit@1 0.625 / hit@3 0.75 / hit@5 0.875, từ chối 4/4 câu ngoài phạm vi.
   Vấn đề: báo cáo còn `pending_human_review` và hit@3 chưa đạt 0.85.
5. Phần "RAG hoặc LoRA → 2 APP" **chưa có**: hiện là 1 app trộn cả hai, nên không chứng minh
   được vai trò của từng thứ. Đây là việc của chặng 5.
6. Tổng thời gian còn lại: **~10 ngày làm việc** (hoặc **1 ngày** nếu chỉ cần bản demo chứng
   minh "đã train và đã tách 2 app").

---

## 1. Đối chiếu 6 ý của thầy với những gì repo đang có

| Ý thầy | Trong repo có gì | Trạng thái | Còn thiếu |
|---|---|---|---|
| Áp dụng LoRA | `configs/llm_sft.yaml` (r=8, alpha=16, dropout 0.05, q/k/v/o_proj, 3 epoch, lr 1e-4, max_len 640); `python/scripts/finetune_llm.py`; `runtime/sft-run-v3/adapter` (thật, có hash) | **CÓ** — đã train, chưa promote | Delta so với base trên test đóng băng; quyết định promote có ký |
| Mã hoá tín hiệu | `dusnx_core.session_signal` + `python/scripts/encode_sessions.py`: mỗi phiên → record không chứa nội dung (`turn_count`, `intents`, `outcomes`, `has_correction`, `has_memory_write`, `signature`) | **CÓ** (tín hiệu dùng để lọc/kiểm) | Tín hiệu chưa được dùng làm **điều kiện chọn mẫu** khi export (hiện chỉ lọc theo số turn) |
| Lấy quá trình làm việc cho vào LoRA | `export_sft_candidates.py` → `runtime/sft-candidates-20261114`: 181 phiên, đã scrub secret/email/hash | **ĐỨT** — 0/181 được duyệt | (a) sửa CSV; (b) duyệt tay; (c) tập train v3 hiện là 105 record `synthetic_designed`, **không** lấy từ phiên thật |
| Huấn luyện lại + quy chuẩn đào tạo | `docs/TRAINING_POLICY.md` v1.0 (14/11): 7 nguyên tắc, 4 điều kiện promote, tiền lệ v3 `promote=false` | **CÓ** nhưng **chưa commit**, chưa có người phản biện thứ hai | Commit + một người review độc lập + báo cáo promote gắn số |
| Tập trung vào 1 dữ liệu | `datasets/domain_corpus_v1`: 1 domain (vận hành / bảo mật / tích hợp DUSN-X), 16 tài liệu khoá hash | **CÓ** | SFT hiện **không** cùng domain với RAG — hai bên đang dạy hai thứ khác nhau (xem mục 2) |
| Lưu trữ 10–20 văn bản | 16/16 trong `sources.txt`, mỗi file có SHA-256 trong `manifest.json` | **ĐẠT** | Không |
| Dùng RAG hoặc LoRA → 2 APP | 1 runtime FastAPI + gateway, có cả RAG FTS5 (161 tài liệu/1.415 chunk) và provider (Gemini/Ollama) | **CHƯA** | Tách 2 app, 2 cổng, 1 kịch bản so sánh cùng câu hỏi |

**Cách nói với thầy (quan trọng hơn code):** đừng nói "em train xong rồi". Nói:
*"Em train 3 vòng, vòng v3 không qua cổng promote vì chưa hơn base trên bộ test đóng băng —
đây là bằng chứng hash, đây là quy chế, và đây là 10 ngày tới em sửa 4 điểm còn thiếu."*
Thầy chấm quy trình + bằng chứng, không chấm việc "có model mới hay không".

---

## 2. Nguyên tắc để "đúng" khi áp dụng LoRA cho chatbot cá nhân

Bốn câu, lấy từ quy chế đã có, và đây là phần thầy sẽ hỏi vấn đáp:

1. **Sự thật thuộc RAG, hành vi thuộc LoRA.** Số liệu, tên máy, mã lỗi, phiên bản, đường dẫn
   → nằm trong tài liệu, để RAG trích `[S1]`. LoRA chỉ học **cách xử sự**: khi nào hỏi lại,
   khi nào từ chối, khi nào xác nhận trước khi hành động, định dạng câu trả lời, cách sửa khi
   người dùng đổi ý.
2. **Không train thứ có thể tra cứu được.** Nếu nhét runbook vào LoRA thì model thuộc lòng số
   liệu cũ, sửa tài liệu phải train lại, và sai số liệu là lỗi nặng nhất của trợ lý cá nhân.
3. **Không duyệt thì không train; test đóng băng trước khi train.** Không chỉnh test sau khi
   xem kết quả; không lấy chính câu test làm dữ liệu train.
4. **Không đo thì không promote.** Candidate phải hơn base trên 4 điều kiện của quy chế, nếu
   không thì `promote=false` — và đó là **quy chế chạy đúng**, không phải thất bại.

Hệ quả cho dự án này: "quá trình làm việc" chỉ vào LoRA ở dạng **hành vi** (hỏi lại cho đủ
ngữ cảnh, từ chối khi thiếu dữ liệu, ghi nhớ có xác nhận, đổi ngôn ngữ theo người dùng,
định dạng câu trả lời), không vào ở dạng nội dung tài liệu.

---

## 3. Bước đi (10 ngày làm việc)

### Chặng 0 — Đóng băng bằng chứng + sửa cổng duyệt (0,5 ngày)

Việc:

1. Sửa `python/scripts/export_sft_candidates.py` dòng ~132–133: thay việc tự ghép chuỗi
   `"\"{json}\""` bằng `csv.writer` để nó tự nhân đôi ngoặc kép. Hiện tại mỗi dòng CSV nở ra
   7–11 cột thay vì 6, cột `decision` bị lệch chỗ.
2. Commit những thứ đang untracked nhưng là bằng chứng: `docs/TRAINING_POLICY.md`,
   `datasets/domain_corpus_v1/` (manifest + sources + test_set), và một
   `docs/evidence/lora-rag/sft-run-v3/artifact_manifest.json` + `metrics.json`
   (không commit adapter weights, chỉ commit hash — theo đúng quy chế "checkpoint không commit").
3. Tạo `docs/evidence/lora-rag/baseline-20261115/README.md` ghi 6 con số: step/epoch,
   train_loss, eval_loss, số record, hash tập dữ liệu, hash adapter.

Cổng: `python csv` đọc `review_queue.csv` ra đúng 6 cột; `git log` có commit chứa policy và
manifest; file evidence mở được bằng đường dẫn.

### Chặng 1 — Chốt tri thức 1 domain cho app RAG (1,5 ngày)

Việc:

1. Giữ nguyên 16 tài liệu đã khoá. Nếu sửa bất kỳ file nào → chạy lại
   `lock_domain_corpus.py` và ghi lý do vào manifest.
2. 20 câu `test_set.jsonl`: đọc tay từng câu, sửa câu nào mà đáp án phải suy luận ngoài tài
   liệu, rồi đóng băng hash. Đổi `review_status` từ `pending_human_review` sang có người duyệt
   thật (tên + thời điểm), không để trạng thái "assistant-drafted".
3. Cải thiện index (đang hit@3 0.75): khi chunk, chèn **tiêu đề mục** vào đầu mỗi chunk để FTS5
   khớp được từ khoá mục; tách chunk theo heading thay vì theo độ dài cố định.
4. Đo lại bằng `evaluate_domain_rag.py`, lưu `evaluation.json` vào evidence.

Lệnh:

```powershell
$env:PYTHONPATH='python/src'; $py='python/.venv/Scripts/python.exe'
& $py python/scripts/lock_domain_corpus.py --check
& $py python/scripts/build_domain_index.py --force
& $py python/scripts/evaluate_domain_rag.py
```

Cổng: hit@3 ≥ 0.85; 4/4 câu ngoài phạm vi vẫn bị từ chối; `citation_present = 1.0`.

### Chặng 2 — Quá trình làm việc → dữ liệu LoRA (2 ngày)

Việc:

1. Thêm bộ lọc theo tín hiệu vào `export_sft_candidates.py`:
   `--min-turns 3 --require-signal correction|memory_write` (hoặc lọc sau, ở bước review).
2. Export lại sau khi có thêm phiên chat thật (máy đang có 181 phiên; **chỉ 11 phiên có
   correction, 44 có memory_write, 79 phiên ≥ 3 turn, 36 phiên thoả cả hai điều kiện** —
   đừng kỳ vọng 181 mẫu).
3. Duyệt **100%** bằng `review_queue.csv` đã sửa: `keep` / `edit` / `drop` + `notes` lý do.
   Dòng `edit` phải được đọc lại sau khi sửa. Mục tiêu thực tế: **35–60 mẫu giữ lại**.
4. Gộp với 105 record synthetic đã duyệt (giữ nhãn `source` để truy vết), khoá tập mới bằng
   `lock_llm_data.py`, ghi hash.
5. Viết lại 20 câu test hành vi (người viết, không phải model): 5 câu thiếu ngữ cảnh phải hỏi
   lại, 5 câu ngoài phạm vi phải từ chối, 5 câu đổi ý giữa chừng, 5 câu định dạng/ngôn ngữ.

Cổng: `train.jsonl` ≥ 150 completion, 0 record `pending`, test 20 câu có tên người viết +
hash, khoá **trước** khi train.

### Chặng 3 — Train lại, có quy chuẩn (1,5 ngày)

Hai nhánh, chọn theo VRAM thật của máy:

- **Nhánh A — giữ 0.5B LoRA** (an toàn, RTX 3050 4 GB chạy được, giữ tính liên tục với v3).
  `python scripts/finetune_llm.py --config configs/llm_sft.yaml --data datasets/llm_sft_v4 --output runtime/sft-run-v4`
- **Nhánh B — khuyến nghị: QLoRA 4-bit Qwen2.5-1.5B** (`qlora: true`,
  `requirements/llm-qlora.txt` = bitsandbytes 0.47.0). Lý do: v3 0.5B **không hơn base** và
  base còn trả lời tiếng Anh khi hỏi tiếng Việt — 0.5B quá nhỏ để giữ hành vi tiếng Việt.

Bất biến giữ nguyên: r=8, alpha=16, dropout 0.05, 3 epoch, lr 1e-4, seed cố định. Không tăng
epoch "cho khớp" — 105–160 mẫu thì 3 epoch là đủ và rất dễ overfit.

Cổng: `training_manifest.json` có `status=training_complete`,
`completion_mask_verified=true`, `lora_update_verified=true`, `data_manifest_status=
human_attested_locked_before_training`.

### Chặng 4 — Đo và quyết định promote (1,5 ngày)

1. Đo offline (không cần Ollama): `evaluate_llm_hf.py --run runtime/sft-run-v4 --data
   datasets/llm_sft_v4 --output runtime/eval-v4-hf.json` — base vs adapter trên **cùng** 20 câu
   test đóng băng.
2. Nếu đã merge/GGUF sang Ollama: `evaluate_llm_pair.py --base qwen2.5:1.5b-instruct
   --candidate <tag> --data datasets/llm_sft_v4 --output runtime/eval-pair-v4.json` chạy qua
   gateway để đo cả đường ống thật.
3. Áp 4 điều kiện của quy chế: không giảm `required_fact_exact`/`forbidden_fact_exact`;
   không tăng trả lời sai khi thiếu dữ liệu; cải thiện ≥ 2/3 chỉ số hành vi (hỏi lại, từ chối,
   định dạng); test ≥ 20 câu người viết đã khoá trước train.
4. Ghi `docs/evidence/lora-rag/eval-v4/README.md` với bảng base/candidate và quyết định
   `promote=true|false` + lý do. Không tự viết attestation, không tự nâng `review_status`.

Cổng: báo cáo có số của cả hai bên; quyết định có chữ ký người; nếu `promote=false` thì ghi rõ
candidate thiếu chỉ số nào.

### Chặng 5 — Tách 2 APP (2 ngày)

Đây là phần thầy nhấn mạnh nhất và hiện chưa có.

**App A — "Trợ lý tài liệu" (RAG)**
- Nguồn: `runtime/domain-rag/rag-domain.db` (16 tài liệu, 224 chunk). Model: base, **không**
  adapter.
- Hợp đồng: trả lời kèm `[S1]…`; ngoài phạm vi 16 tài liệu → từ chối, không bịa; không tư vấn
  ngoài tài liệu.
- Số đo: hit@3, `citation_present`, tỉ lệ từ chối đúng.

**App B — "Trợ lý quy trình" (LoRA)**
- Model: adapter v4 (đã promote hoặc không, ghi rõ trong UI). **Tắt RAG** — thêm cờ
  `DUSNX_RAG_ENABLED=0` (~10 dòng trong `python/apps/ai_api/rag.py` + đọc ở `main.py`), hoặc
  trỏ `DUSNX_RAG_DB` vào một DB rỗng có chủ đích.
- Hợp đồng: không bịa số liệu; thiếu ngữ cảnh → hỏi lại; người dùng đổi ý → xác nhận lại;
  định dạng/ngôn ngữ theo người dùng.
- Số đo: tỉ lệ hỏi lại đúng, tỉ lệ từ chối đúng, tỉ lệ giữ định dạng.

**Cách chạy 2 app**: hai script `start-app-a.ps1`, `start-app-b.ps1` (port 8081/8082), dùng
chung gateway tĩnh; hoặc một `docker-compose` với 2 service.

**Kịch bản demo 6 câu (chạy trên cả 2 app, ghi bảng 6×2):**

| # | Câu hỏi | App A phải làm | App B phải làm |
|---|---|---|---|
| 1 | "Port AI API và gateway đang chạy là bao nhiêu?" | Trả lời đúng + `[S1]` | Không bịa; nói cần tra tài liệu |
| 2 | "Lệnh restart native thế nào?" | Trích runbook, đúng cú pháp | Trả lời theo khuôn, không tự bịa lệnh |
| 3 | "Bản backup gần nhất nằm ở đâu?" | Trích đúng mục, kèm nguồn | Nói rõ không có dữ liệu → hỏi lại/khước từ |
| 4 | "Viết lại câu này ngắn hơn, giữ ý" | Có thể trả lời nhưng không ưu tiên | Làm đúng, giữ định dạng |
| 5 | "Thôi đổi ý, dùng phương án B" (sau khi đã chốt A) | Hỏi lại cho rõ ngữ cảnh | Xác nhận thay đổi, không lặp lại A |
| 6 | "Cho tôi số liệu doanh thu 2027" (không có trong tài liệu) | Từ chối, chỉ ra ngoài phạm vi | Hỏi lại/thu hẹp, không bịa |

Cổng: bảng 6×2 có khác biệt **giải thích được**; App A không làm việc hành vi, App B không
bịa số liệu.

---

## 4. Song song: hồ sơ nộp thầy (0,5 ngày, làm cùng chặng 5)

Một trang `docs/evidence/lora-rag/README.md` gồm:

1. Sơ đồ: dữ liệu → tín hiệu → duyệt tay → khoá → train → đo → promote/từ chối.
2. Bảng 4 vòng: v1/v2/v3 (và v4) với `promote` + lý do.
3. 6 con số của v3 + hash dữ liệu + hash adapter.
4. Bảng 2 app với kịch bản 6 câu ở trên.
5. Mục "điều chưa làm được": 0.5B yếu, hit@3 0.75, 181 phiên chưa duyệt hết, test do AI soạn
   trước khi có người viết. Thầy sẽ tin phần này hơn phần khoe.

---

## 5. Rủi ro và cách chặn

| Rủi ro | Dấu hiệu | Cách chặn |
|---|---|---|
| 0.5B không đủ giữ hành vi tiếng Việt | candidate không hơn base, trả lời tiếng Anh | Nhánh B QLoRA 1.5B; giữ 0.5B chỉ làm baseline |
| Overfit trên 105–160 mẫu | eval_loss tăng 2 lần liên tiếp, trả lời thuộc lòng câu train | 3 epoch, early stop patience 2, giữ validation tách theo phiên |
| Duyệt tay 181 phiên quá lâu | trễ 2 ngày | lọc tín hiệu trước (36–79 phiên), duyệt 100% nhưng trên tập đã lọc |
| Train nội dung tài liệu vào LoRA | model trả lời số liệu cũ, không trích nguồn | Nguyên tắc 1; review từng dòng, `drop` mọi mẫu dạy dữ kiện |
| Test do AI soạn → điểm ảo | điểm cao nhưng demo sai | 20 câu người viết, người thứ hai duyệt trước khi xem prediction |
| App B lén dùng RAG | App B trả lời đúng số liệu | Cờ tắt RAG + test "App B không được biết số liệu" |
| Bằng chứng nằm ngoài git | thầy mở repo không thấy | Chặng 0: commit policy + manifest + evidence; adapter chỉ commit hash |

---

## 6. Nếu chỉ có 1 buổi để chứng minh (bản rút gọn 1 ngày)

1. Sửa CSV (30 phút) → duyệt 20 phiên mạnh nhất (`has_correction` hoặc ≥ 3 turn).
2. Commit policy + corpus + manifest (30 phút).
3. Tạo 2 script chạy 2 app với cấu hình sẵn có (không train lại): App A RAG-only, App B
   adapter v3 + RAG off (2 giờ).
4. Chạy kịch bản 6 câu, chụp màn hình 12 dòng kết quả (2 giờ).
5. Nói rõ: "v3 chưa promote vì chưa hơn base; 10 ngày tới là v4 + tách app hoàn chỉnh".

Bản này **không** hứa model tốt hơn, nhưng chứng minh được: có train, có quy chế, có 2 app,
có số đo — đúng 3 thứ thầy đang thiếu.

---

## 7. Ba câu cần thầy chốt (hỏi một lần, đừng hỏi rải)

1. **Domain**: giữ "vận hành/bảo mật/tích hợp DUSN-X" (16 tài liệu sẵn có) hay đổi sang domain
   khác gần nhu cầu thật hơn? Đổi domain = làm lại chặng 1 + 2.
2. **App B dùng model ngoài 0.5B** (Qwen2.5-1.5B QLoRA) có được chấp nhận là "dùng LoRA" không,
   hay bắt buộc đúng base 0.5B đã đăng ký?
3. **Ai viết 20 câu test**: thầy, một bạn khác, hay em viết rồi người thứ hai duyệt? (Quy chế
   yêu cầu người viết ≠ người train; nếu em viết thì cần người duyệt độc lập trước khi train.)

---

## 8. Bảng tiến độ tóm tắt

| Chặng | Nội dung | Ngày | Đầu ra kiểm được |
|---|---|---|---|
| 0 | Đóng băng bằng chứng, sửa CSV | 0,5 | commit + CSV 6 cột |
| 1 | Chốt tri thức RAG | 1,5 | hit@3 ≥ 0.85, test đóng băng |
| 2 | Quá trình làm việc → SFT | 2 | train ≥ 150, 0 pending |
| 3 | Train v4 (LoRA hoặc QLoRA) | 1,5 | training_manifest complete |
| 4 | Đo + promote | 1,5 | eval-v4 có số, quyết định |
| 5 | Tách 2 app + demo | 2 | bảng 6×2 |
| — | Hồ sơ nộp thầy | 0,5 | `docs/evidence/lora-rag/README.md` |

Tổng: **9,5 ngày làm việc**, dư 0,5 ngày đệm.
