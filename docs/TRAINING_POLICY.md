# Quy chế đào tạo DUSN-X

Phiên bản 1.0 — 2026-11-14. Chủ sở hữu: Doanh. Người phản biện độc lập cho
tập test: Quynh (theo tiền lệ v3). Mọi thay đổi quy chế phải ghi ngày và lý do.

## 1. Phạm vi

Quy chế này áp dụng cho mọi lần huấn luyện LoRA, mọi tập dữ liệu SFT, và mọi
quyết định promote model của DUSN-X. Nó không áp dụng cho RAG: RAG là dữ liệu
tra cứu, không phải trọng số, và được cập nhật bằng cách index lại.

## 2. Bảy nguyên tắc bất biến

1. **Sự thật thuộc về RAG, hành vi thuộc về LoRA.** Không huấn luyện model để
   thuộc lòng số liệu, mã định danh, giá trị cấu hình hay thông tin cá nhân.
2. **Không train trên dữ liệu chưa duyệt.** Trạng thái `pending` không được vào
   tập train.
3. **Test không được dùng để train.** Tập test đóng băng trước khi train và
   không được sửa sau khi xem kết quả.
4. **Không promote nếu không đo.** Không có báo cáo so sánh base/candidate thì
   không có quyết định promote.
5. **Không tạo bằng chứng.** Không tự viết attestation, không tự nhận "người
   duyệt", không nâng `review_status` bằng script.
6. **Không có bí mật trong dữ liệu.** Email, token, khoá, hash dài, đường dẫn
   cá nhân phải bị loại trước khi lưu.
7. **Mọi con số phải truy được.** Mỗi báo cáo phải chỉ ra file, hash, ngày đo
   và lệnh đã chạy.

## 3. Nguồn dữ liệu hợp lệ

| Nguồn | Được dùng | Điều kiện |
|---|---|---|
| Phiên chat thật trên máy | Có | Export read-only, scrub, duyệt tay từng dòng |
| Kịch bản thiết kế (`synthetic_designed`) | Có | Ghi rõ `generation_method`, người review |
| Tài liệu dự án làm ngữ cảnh RAG | Có | Chỉ index, không đưa vào SFT |
| Dữ liệu sinh viên/khách hàng thật | Không | Chỉ dùng dữ liệu tổng hợp hoặc ẩn danh |
| Dữ liệu tải về không rõ giấy phép | Không | — |
| Đầu ra model chưa qua người | Không | Model tự sinh không phải dữ liệu vàng |

## 4. Quy trình bắt buộc

1. **Khoá corpus** (một domain, 10–20 văn bản):
   `python python/scripts/lock_domain_corpus.py`
   → `datasets/domain_corpus_v1/manifest.json` (SHA-256 từng file).
2. **Dựng index theo phạm vi**:
   `python python/scripts/build_domain_index.py --force`
   → `runtime/domain-rag/rag-domain.db`. Không đụng `python/data/rag.db`.
3. **Thu tín hiệu phiên làm việc**:
   `python python/scripts/export_sft_candidates.py`
   → `runtime/sft-candidates-<ngày>/candidates.jsonl` + `review_queue.csv`.
4. **Duyệt tay**: điền `decision` (`keep` / `edit` / `drop`) và `notes` vào
   `review_queue.csv`. Chỉ `keep`/`edit` mới được chuyển sang tập train; dòng
   `edit` phải được đọc lại sau khi sửa.
5. **Khoá tập SFT**: tạo `train/validation/test.jsonl`, chạy script lock của
   project, ghi hash vào manifest. Tập test do người viết, không do model.
6. **Train** trong môi trường riêng (`requirements/llm-sft.txt`):
   `python scripts/finetune_llm.py --config configs/llm_sft.yaml --data <tập đã khoá> --output runtime/sft-run-<id>`
7. **Đo và quyết định**: chạy `evaluate_llm_pair.py` trên tập test đóng băng,
   ghi báo cáo vào `docs/evidence/llm-sft/<id>/`, rồi mới promote hoặc không.

## 5. Chia tập và đóng băng

- **Train**: phiên thật đã duyệt + kịch bản thiết kế đã review.
- **Validation**: tách theo phiên, không tách theo lượt (tránh rò rỉ cùng phiên).
- **Test**: người viết, tối thiểu 20 câu cho một domain, phủ cả câu ngoài phạm vi
  để đo từ chối. Tập test không xuất hiện trong RAG corpus.
- Mọi tập phải có hash và ngày khoá. Sửa tài liệu nguồn thì phải khoá lại và
  ghi lý do; test xanh của repo sẽ đỏ nếu manifest lệch.

## 6. Siêu tham số

Dùng đúng `configs/llm_sft.yaml` trừ khi có lý do bằng văn bản:
`lora_r=8`, `lora_alpha=16`, `lora_dropout=0.05`, target `q/k/v/o_proj`,
`epochs=3`, `lr=1e-4`, `batch=1`, `grad_accum=8`, `max_length=640`, seed cố định.
Không tăng epoch để "cho khớp"; dữ liệu ít thì 3 epoch là đủ và dễ overfit.

## 7. Ngưỡng promote

Một candidate chỉ được promote khi **tất cả** điều kiện sau đúng:

1. Không giảm `required_fact_exact` và `forbidden_fact_exact` so với base trên
   cùng bộ test.
2. Không tăng tỉ lệ trả lời sai khi thiếu dữ liệu (phải từ chối hoặc hỏi lại).
3. Cải thiện rõ ít nhất 2 trong 3 chỉ số hành vi (hỏi lại, từ chối, định dạng).
4. Bộ test có tối thiểu 20 câu người viết, đã đóng băng trước khi train.

Tiền lệ v3: candidate không hơn base (`required_fact` 4/8 cả hai bên,
`forbidden_fact` 8/8 → 7/8, `clarification` 5/8 cả hai) nên quyết định là
`promote=false`. Đây là quy chế chạy đúng, không phải thất bại.

## 8. Rollback

- Giữ nguyên adapter cũ và GGUF cũ trong `runtime/` cho đến khi candidate được
  promote và chạy ổn định.
- Promote phải kèm đường lùi: đổi `DUSNX_OLLAMA_MODEL` về model cũ trong một
  lệnh, không cần build lại.
- Nếu phát hiện model trả lời sai sự thật, ưu tiên gỡ model khỏi runtime rồi
  mới điều tra dữ liệu.

## 9. Khi nào được retrain

Chỉ retrain khi có ít nhất một trong các điều kiện:

- Có nhóm lỗi hành vi được đo lặp lại trên ≥ 5 phiên thật.
- Có ≥ 50 cặp mới đã duyệt.
- Corpus đổi cấu trúc (thêm domain mới), khi đó train lại từ đầu thay vì trộn.
- Model nền đổi phiên bản hoặc revision.

Không retrain để "chữa" một lỗi retrieval: sửa corpus/index trước.

## 10. Bị cấm

- Train trên tập test, hoặc chỉnh test sau khi xem kết quả.
- Promote khi chưa có báo cáo so sánh.
- Ghi "human_reviewed" cho dữ liệu chưa ai đọc.
- Đưa bí mật, token, email, dữ liệu cá nhân vào dataset hoặc log.
- Dùng LoRA để nhớ dữ liệu tra cứu thay vì RAG.
- Tự nhận đã kiểm thử giao diện khi chỉ chạy unit test.

## 11. Bằng chứng phải lưu

Mỗi lần train phải có: manifest dữ liệu + hash, cấu hình, log train, thư mục
`adapter/`, báo cáo so sánh, quyết định promote kèm người quyết định và ngày.
Thiếu một mục thì lần train đó không được tính là đã hoàn thành.
