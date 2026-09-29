# Nguồn dữ liệu DUSN-X

Kiểm tra ngày 2026-09-29. Revision máy đọc được trong `configs/data_sources.json`.
Không commit raw data, worker IDs, token hoặc parquet. Chỉ dữ liệu public được tải tự động.

| Nguồn | Revision | License dữ liệu | Truy cập và mục đích |
|---|---|---|---|
| [CSConDa](https://huggingface.co/datasets/ura-hcmut/Vietnamese-Customer-Support-QA) | `4656fb2ebd5e2ea0953a6752f1dcb21d0d49966d` | Apache-2.0 theo card | Manual gate; chưa được cấp quyền, **chưa tải dữ liệu**. Adapter QA để kiểm tra sau khi được duyệt. |
| [MASSIVE](https://huggingface.co/datasets/AmazonScience/massive) | `ff6bd8e4b27c3543e4f8fe2108f32bb95a6f8740` | CC-BY-4.0 | Public; chỉ vi-VN, chỉ intent được duyệt. |
| [SGD](https://github.com/google-research-datasets/dstc8-schema-guided-dialogue) | GitHub `e852981ae34990f4358979625854259302feaa78` | CC-BY-SA-4.0 (data), Apache-2.0 (code) | Tham khảo schema nhiều lượt; không đưa câu tiếng Anh vào train. |

HF SGD tương ứng là [schema_guided_dstc8](https://huggingface.co/datasets/google-research-datasets/schema_guided_dstc8), revision `bf400d9a91201a3438b552cf95f0c20dd884b1bf`. Tên repository HF khác tên GitHub trong yêu cầu.

CSConDa card khai báo `question`, `answer`, `type`, train 8.349 / test 1.500. Loại General/Simple/Complex không phải intent/agent/action của DUSN-X. Chưa kiểm tra mẫu raw vì chưa có quyền. Đăng nhập HF, đọc điều kiện, gửi yêu cầu và đợi chủ dataset duyệt. Sau đó đặt `HF_TOKEN` qua môi trường/Colab Secrets và chạy `fetch_sources.py --source csconda --allow-gated`. Script không tự tìm token hoặc vượt gate; mặc định bỏ qua nguồn này. Xem [quy trình gated datasets](https://huggingface.co/docs/hub/datasets-gated).

MASSIVE đã tải thật từ archive v1.1 mà loader HF ở revision trên chỉ định: [archive của Amazon](https://amazon-massive-nlu-dataset.s3.amazonaws.com/amazon-massive-dataset-1.1.tar.gz). Không thực thi remote loader. SHA-256 archive: `4cba5faa11c71437928e17cb1b9b3d8b8e727e7ea363a3a9a8045e19c0491577`; vi-VN: `9dfff36bac20067085d836c30f1a617de968c16fd81bf4c5b802ddd637ab131a`. Archive đa ngôn ngữ được tải, chỉ member vi-VN được đọc ra.

Đã inspect 16.521 câu: train 11.514, dev 2.033, test 2.974. Trường gồm `id, locale, partition, scenario, intent, utt, annot_utt, worker_id, slot_method, judgments`. Mẫu public kiểm tra: “cho tôi biết dưới đất ngầm có nghĩa là gì” → `qa_definition`. Import không giữ worker_id, không suy ra agent/action/state. Mỗi câu giữ `single_turn`, user/sequence riêng. `configs/massive_vi_mapping.json` là **đề xuất chờ duyệt**, không phải mapping đã được duyệt. Vì vậy các candidate hiện không có nhãn train.

SGD đã tải thật **hai file tham khảo** `train/schema.json` và `train/dialogues_001.json`, không tải toàn bộ. Dialogue gồm dialogue_id, services, turns; turn có speaker, utterance, frames; frame gắn service, actions và state (active_intent, requested_slots, slot_values). Đây là gợi ý cấu trúc annotation, không phải phép ánh xạ trực tiếp sang agent DUSN-X. Không phân phối lại raw samples trong repo.

## Inspect, lọc và nguồn gốc

```bash
python python/scripts/fetch_sources.py --source all
python python/scripts/import_data.py --source massive --input runtime/external-data/massive/vi-VN.jsonl --output-dir runtime/imported/massive
python python/scripts/prepare_data.py --legacy data/synthetic_30k_v2.jsonl --external runtime/imported/massive/candidates.jsonl
```

Inspect chạy trước import, lấy mẫu seed cố định và redaction. Kiểm tra PII là heuristic (email, số định danh/điện thoại, secret, cue địa chỉ/tên), **không bảo đảm phát hiện mọi PII**; reviewer phải kiểm tra thêm. Báo cáo lưu `inspection.json`, `report.json`; lọc source split, locale, độ dài, PII, câu trùng NFC/casefold và intent không ánh xạ. Dòng không được duyệt không lọt vào prepare/train. Nhãn agent/action thiếu được mask `-100`, không gán giả.

30.000 event synthetic có sẵn có 1.000 chuỗi nhưng chỉ 244 câu riêng biệt (99,19% lặp câu). Metadata cũ không có ID template, nên không khẳng định có 1.000 template. Pipeline giới hạn 100 chuỗi cũ (3.000 event), bổ sung bank thiết kế 9 trajectory × 4 cách diễn đạt; giới hạn tối đa 8 bộ thực thể mỗi nhóm. `synthetic_designed` ghi nguồn từng event, state annotation và provenance nhãn; không gọi là hội thoại thật. Các style validation khác style train nhưng vẫn cùng họ trajectory: validation còn dễ, không độc lập hoàn toàn.

Chỉ tăng tới hàng chục nghìn event sau khi có thêm họ tình huống, kiểm tra PII/duplicate, reviewer và phân bố nhãn đủ đa dạng. Hiện **dừng tăng quy mô** vì độ lặp cao. Train học recurrent state và route heads bằng loss phân loại; state annotation phục vụ review, không phải target trực tiếp của memory SQL. Không huấn luyện LLM sinh văn bản.
