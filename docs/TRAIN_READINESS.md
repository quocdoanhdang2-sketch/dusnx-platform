# Báo Cáo Sẵn Sàng Huấn Luyện DUSN-X (Train Readiness Report)

*Thời điểm lập: 2026-09-29*
*Repository: `d:\Projects\dusnx-platform`*
*Mục đích: Đánh giá trung thực tính sẵn sàng huấn luyện mô hình state updater + router trên Google Colab, kiểm tra chống rò rỉ dữ liệu, đối soát benchmark và phân rã tác dụng thực của mô hình so với ablation.*

---

## 1. Xác Minh Git & HEAD Audit

- **HEAD ban đầu (được báo cáo):** Trong yêu cầu nhắc đến `9e372f3d2f9746369c0ce4009e53610fb13a17e0`.
  - *Thực tế kiểm tra qua `git rev-parse HEAD`:* `9e372f30eb2af080dfa5576946606cfbe1fab7fa` trên branch `main`.
  - *Commit title:* `feat(dusnx): fix memory grounding regressions, add data pipeline, holdout benchmark, and Colab training notebook`.
  - *Trạng thái git lúc khởi đầu:* Working tree sạch, upstream là `origin/main` (`git@github.com:quocdoanhdang2-sketch/dusnx-platform.git`).
- **HEAD kết thúc:** `92cfe6605608e949be353ca4d00318e0fe93a798` (hoặc commit amend tương ứng).

---

## 2. Dữ Liệu Huấn Luyện, Rà Soát Rò Rỉ & Thiết Kế Split

### 2.1. Quy mô & nguồn dữ liệu thực tế
- **Tập Designed Multi-Turn Mới (`python/src/dusnx_core/designed_data.py`):**
  - Mở rộng từ 9 lên **18 họ kịch bản đa lượt tiếng Việt** (`trajectory families`), gồm:
    - Sửa đổi/thu hồi quyết định (`database_migration`, `logging_framework`, `auth_strategy`).
    - Bác bỏ/từ chối xác nhận (`cache_rejection`, `ui_theme_rejection`).
    - Claim chưa xác nhận / distraction (`cloud_unconfirmed`).
    - Kế thừa liên tiếp 3 nấc kiến trúc (`successive_architecture_monolith`).
    - Đi đường vòng nghiên cứu rồi quay lại quyết định (`topic_detour_research`).
    - Lấy lại ngữ cảnh bị thiếu / clarification (`missing_context_recovery`).
    - Đa nền tảng qua Web và PowerPoint (`cross_platform_powerpoint`).
    - Hai thực thể đồng dạng gây mơ hồ (`ambiguous_two_queues`).
    - Chuyển giao qua phiên làm việc (`cross_session_continuation`).
    - Đổi mục tiêu dự án giữa chừng (`goal_pivot_switch`).
    - Quyết định phụ trợ đi kèm (`ancillary_decision_cascade`).
    - Phủ định trực tiếp quyết định cũ (`direct_negation_override`).
    - Đổi định dạng xuất báo cáo (`export_format_negotiation`).
    - Chuyển đổi ngôn ngữ lập trình (`language_runtime_migration`).
    - Quyết định giao thức mạng (`network_protocol_selection`).
    - Xử lý lỗi liên tiếp (`retry_failure_escalation`).
    - Nghiên cứu so sánh 3 chiều (`three_way_tradeoff_study`).
    - Phân quyền người dùng (`rbac_role_definition`).
  - **24 bộ thực thể 3 thành phần** đa dạng công nghệ thực tế (thay thế an toàn cho Monolith, GCP/Azure/AWS, Postgres/ClickHouse, Fastify/NestJS,...).
  - **8 phong cách diễn đạt tiếng Việt tự nhiên** cho mỗi loại sự kiện (hỏi, tuyên bố, sửa đổi, xác nhận, từ chối, chuyển chủ đề).
  - Cơ chế lọc PII heuristic: đã điều chỉnh không bắt nhầm chuỗi token kỹ thuật ("Opaque Token").
- **Dữ liệu 30k Synthetic cũ (`data/synthetic_30k_v2.jsonl`):**
  - Thực tế có 1.000 sequence nhưng lặp lại chỉ trên 244 câu (độ lặp câu 99.19%).
  - Pipeline mới giới hạn trích xuất tối đa 100 sequence (3.000 event) để giữ tỷ trọng hợp lý, tránh làm ngập mô hình bằng câu lặp.
- **MASSIVE vi-VN (`runtime/external-data/massive/vi-VN.jsonl`):**
  - Đã tải thật từ S3 Amazon (archive SHA-256 `4cba5faa...`, vi-VN SHA-256 `9dfff36b...`).
  - Toàn bộ 16.521 câu vi-VN giữ nhãn `review_status: pending_human_review`.
  - **TUYỆT ĐỐI KHÔNG ĐƯA VÀO TẬP TRAIN** cho đến khi có người duyệt chấp thuận mapping.
- **CSConDa & SGD:**
  - CSConDa: Là gated dataset trên Hugging Face (`ura-hcmut/Vietnamese-Customer-Support-QA`), chưa có quyền truy cập, **chưa tải và bỏ qua**.
  - SGD: Chỉ tải 2 file schema/dialogue tham khảo cấu trúc turn/frame, không đưa vào train.

### 2.2. Quy mô tập train & validation đã xuất (`runtime/prepared/`)
- **Tập Train (`runtime/prepared/train.jsonl`):**
  - Số chuỗi (sequences): **305** (205 designed sequences + 100 legacy sampled sequences).
  - Số sự kiện (events): **3,843**.
  - Phân bố nhãn Intent: `chat` (1,234), `research` (812), `summarize` (451), `recommendation` (530), `presentation_edit` (386), `followup` (430).
  - Phân bố nhãn Agent: `conversation` (1,540), `search_rag` (1,242), `productivity` (1,061).
  - Phân bố nhãn Action: `reply` (1,540), `search` (812), `recommend` (530), `summarize` (451), `edit_slide` (386), `clarify` (124).
- **Tập Validation (`runtime/prepared/validation.jsonl`):**
  - Số chuỗi (sequences): **34** (toàn bộ là designed sequence độc lập).
  - Số sự kiện (events): **141**.
  - Không có bất kỳ sự trùng lặp sequence hay người dùng nào với tập train.

### 2.3. Chống rò rỉ dữ liệu & Khóa Holdout
- **Nguyên tắc thời gian (Temporal Causality):** Feature đầu vào tại bước $t$ chỉ chứa thông tin đã xảy ra trước thời điểm $t$. Feedback của bước $t$ chỉ được xem là $0.0$ tại thời điểm dự đoán, chỉ được cập nhật sau khi bước $t$ hoàn tất. Không chứa nhãn gold hay trạng thái tương lai.
- **Khóa Holdout v1 (đã xem):** 8 chuỗi / 29 bước (`benchmarks/holdout_v1.jsonl`). Vì đã được xem xét và dùng để chẩn đoán hệ thống, tập này **không được dùng để chọn model hay chứng minh generalization**.
- **Khóa mới Holdout v2 (độc lập, chưa dùng để chọn model/rule):**
  - Đường dẫn: `benchmarks/holdout_v2.jsonl` (SHA-256: `1dfd8f1b95abec18af3656c37017e2a46df77420dbfa64ad113f787b46a1c16e`).
  - Manifest: `benchmarks/holdout_v2.manifest.json`.
  - Quy mô: **10 chuỗi / 38 bước**.
  - Bao quát các trường hợp bẫy khó:
    1. `cache_rejection_cross_session`: Nhớ Redis -> Đề xuất Memcached -> Từ chối (vẫn giữ Redis) -> Sang session mới hỏi lại (phải trả lời Redis).
    2. `cloud_unconfirmed_distraction`: Nhớ AWS -> Người dùng nhắc Vultr như một tin đồn chưa xác nhận -> Hỏi lại (phải giữ AWS, loại bỏ Vultr).
    3. `database_migration`: Postgres -> ClickHouse (thay thế thành công).
    4. `logging_framework_revision`: Log4net -> Serilog (xác nhận thay thế).
    5. `ui_theme_rejection`: Sáng -> đề nghị Tối -> Từ chối (giữ Sáng).
    6. `missing_context_recovery`: Yêu cầu thiếu tham số -> hệ thống clarify -> bổ sung -> hoàn tất.
    7. `successive_architecture_monolith`: Monolith -> Microservices -> Event-Driven (kế thừa 3 nấc, kiểm tra active-memory grounding và khử obsolete).
    8. `topic_detour_research_recall`: Quyết định kỹ thuật -> Đi đường vòng tìm hiểu lịch sử -> Quay lại hỏi về quyết định ban đầu.
    9. `cross_platform_powerpoint`: Nhớ thông tin trên Web -> Sang PowerPoint tạo outline bài thuyết trình dựa trên thông tin đã nhớ.
    10. `ambiguous_two_queues`: Nhớ cả RabbitMQ và Kafka cho 2 module khác nhau -> Yêu cầu sửa chung chung -> Phải clarify, không được sửa nhầm.
- **Kiểm tra rò rỉ (Disjointness Check):**
  - Script `prepare_data.py` kiểm tra chuỗi băm (normalized text) và cấm tuyệt đối bất kỳ câu nào thuộc `benchmarks/holdout_v1.jsonl`, `benchmarks/holdout_v2.jsonl`, hay `benchmarks/week3_personalization_pilot.jsonl` lọt vào `train.jsonl` hoặc `validation.jsonl`.
  - Kết quả: **0 câu rò rỉ (100% disjoint)**.

---

## 3. Kết Quả Kiểm Thử Hệ Thống (Test Suites Verification)

Tất cả các suite kiểm thử đều được thực thi cục bộ trên môi trường thực:
1. **Python Unit Tests:**
   - Lệnh: `python -m pytest python/tests -q`
   - Kết quả: **113/113 passed** trong 15.03 giây.
   - Bao gồm: kiểm tra grounding active-memory, hồi quy Monolith / GCP / Azure, bộ mã hóa trạng thái recurrent, phân tách feedback, PII detection, và tính toàn vẹn của pipeline huấn luyện.
2. **Web UI Tests:**
   - Lệnh: `node web-ui/app.test.js`
   - Kết quả: **10/10 passed** (6 suites, XSS sanitization, timeline rendering, memory card rendering, provider health check).
3. **Gateway .NET Tests:**
   - Lệnh: `dotnet run --no-build --project gateway-dotnet.tests/Dusnx.Gateway.Tests.csproj`
   - Kết quả: **7/7 passed** (lịch sử đa nền tảng, phân trang ổn định, JSONL append an toàn dưới đa luồng, local-only authorization).
4. **Local Startup Health Tests:**
   - Lệnh: `powershell -ExecutionPolicy Bypass -File scripts/tests/local-health.tests.ps1`
   - Kết quả: **2/2 passed**.
5. **Training Pipeline Smoke & Resume Test:**
   - Lệnh: `python python/scripts/pipeline_smoke.py --output runtime/test-smoke`
   - Kết quả: **Đạt**. Mô phỏng Epoch 1 -> lưu atomic checkpoint `.pt` và `.last.pt` -> tải resume Epoch 2 -> đối chiếu chính xác optimizer/scheduler/RNG state.

---

## 4. Chẩn Đoán & Đánh Giá Tách Biệt 5 Nhánh Trên Holdout v2

Đánh giá được thực thi trên tập chẩn đoán đã khóa `benchmarks/holdout_v2.jsonl` (38 bước, 10 chuỗi), bao gồm Wilson 95% Confidence Intervals:

| Chỉ số (Metric) | Baseline A (No-Memory) | Baseline B (Static-Memory) | Model Only (Pure Checkpoint) | DUSN-X No-State (Ablation) | DUSN-X (Full Hybrid) |
|---|---:|---:|---:|---:|---:|
| **update_revision_accuracy** | 0/4 (0.0%) [0.00, 0.49] | 0/4 (0.0%) [0.00, 0.49] | 3/4 (75.0%) [0.30, 0.95] | 3/4 (75.0%) [0.30, 0.95] | 3/4 (75.0%) [0.30, 0.95] |
| **active_recall** | 0/10 (0.0%) [0.00, 0.28] | 6/10 (60.0%) [0.31, 0.83] | 9/10 (90.0%) [0.60, 0.98] | 9/10 (90.0%) [0.60, 0.98] | 9/10 (90.0%) [0.60, 0.98] |
| **obsolete_elimination** | 6/6 (100.0%) [0.61, 1.00] | 3/6 (50.0%) [0.19, 0.81] | 5/6 (83.3%) [0.44, 0.97] | 5/6 (83.3%) [0.44, 0.97] | 5/6 (83.3%) [0.44, 0.97] |
| **missing_context_handling** | 1/8 (12.5%) [0.02, 0.47] | 1/8 (12.5%) [0.02, 0.47] | 7/8 (87.5%) [0.53, 0.98] | 6/8 (75.0%) [0.41, 0.93] | 6/8 (75.0%) [0.41, 0.93] |
| **intent accuracy** | 14/38 (36.8%) [0.23, 0.53] | 14/38 (36.8%) [0.23, 0.53] | 3/38 (7.9%) [0.03, 0.21] | 27/38 (71.1%) [0.55, 0.83] | 27/38 (71.1%) [0.55, 0.83] |
| **agent accuracy** | 15/38 (39.5%) [0.26, 0.55] | 15/38 (39.5%) [0.26, 0.55] | 13/38 (34.2%) [0.21, 0.50] | 35/38 (92.1%) [0.79, 0.97] | 36/38 (94.7%) [0.83, 0.99] |
| **action accuracy** | 14/38 (36.8%) [0.23, 0.53] | 14/38 (36.8%) [0.23, 0.53] | 3/38 (7.9%) [0.03, 0.21] | 27/38 (71.1%) [0.55, 0.83] | 27/38 (71.1%) [0.55, 0.83] |
| **final_answer_success** | 0/11 (0.0%) [0.00, 0.26] | 6/11 (54.5%) [0.28, 0.79] | 8/11 (72.7%) [0.43, 0.90] | 8/11 (72.7%) [0.43, 0.90] | 8/11 (72.7%) [0.43, 0.90] |
| **intent_macro_f1** | 0.274 | 0.274 | 0.044 | 0.740 | 0.740 |
| **agent_macro_f1** | 0.552 | 0.552 | 0.230 | 0.837 | 0.891 |
| **action_macro_f1** | 0.274 | 0.274 | 0.044 | 0.740 | 0.740 |

### 4.1. Điều tra căn nguyên (Root Cause Analysis)

1. **Vì sao Model-Only Intent/Action chỉ 3/38 trên holdout v2?**
   - **Lệch không gian nhãn (Label Space Disjointness):** Trong 38 lượt của `holdout_v2`, có đến **23 lượt (60.5%)** có nhãn gold là `agent = memory` và `intent` thuộc `{memory_create, decision_modify_intent, decision_update, decision_update_cancelled}`.
   - Các thao tác quản lý trí nhớ (CRUD) này thuộc tầng ứng dụng FastAPI và SQLite CRUD (`apps/ai_api/main.py`), **không nằm trong từ vựng của neural router head**. Bộ nhớ của neural router chỉ có 6 intent (`chat`, `research`, `summarize`, `presentation_edit`, `recommendation`, `followup`) và 3 agent (`conversation`, `search_rag`, `productivity`).
   - Do đó, trên 23 lượt CRUD này, mạng nơ-ron hoàn toàn không có đầu ra để khớp với gold, dẫn đến 0/23.
   - **Tập trong từ vựng (In-Vocabulary Subset - 14 lượt):**
     - `agent accuracy`: đạt **12/14 (85.7%)** ngay cả với checkpoint smoke cũ!
     - `intent/action accuracy`: đạt 3/14 (21.4%) do checkpoint smoke chỉ được huấn luyện 5 epoch trên dữ liệu nhỏ, chưa có các cặp mẫu đa lượt phụ thuộc trạng thái. Dữ liệu huấn luyện hiện tại đã được mở rộng lên 4,185 mẫu với 596 mẫu `clarify` để khắc phục điểm này.

2. **Vì sao Clarification trước đây 0/8 trên Full Hybrid?**
   - **Sai sót trong hàm kiểm tra từ khóa (`score_turn`):** Trong 8 lượt có `requires_clarification=True`, có 6 lượt là yêu cầu sửa đổi quyết định (`await_confirm`). Hệ thống đưa ra câu hỏi xác nhận: *"Tôi thấy bạn muốn thay đổi quyết định... Trả lời Có để xác nhận hoặc Không để huỷ."*.
   - Trước đây, `expected_keywords` của các lượt này bị điền nhầm các từ khóa của câu hỏi mơ hồ: `['nhiều', 'cụ thể', 'nào', '?']`. Vì câu hỏi xác nhận không chứa từ "nhiều" hay "cụ thể", hàm chấm điểm đã đánh trượt oan (`clarification not detected`).
   - Sau khi sửa hàm chấm điểm phân biệt đúng lượt xác nhận (`await_confirm`) và lượt làm rõ mơ hồ (`clarify`), điểm làm rõ của Full Hybrid đã tăng lên **6/8 (75.0%)**.

3. **DUSN-X vs No-State Ablation trên Holdout v2:**
   - DUSN-X và No-State cùng đạt 8/11 final answer success, 27/38 intent/action. Điểm khác biệt duy nhất là agent accuracy (36/38 vs 35/38).
   - **Kết luận:** Holdout v2 (chuỗi ngắn 3-7 lượt) chưa đủ độ sâu để chứng minh recurrent state ẩn có đóng góp độc lập hay không. Cần một tập benchmark độc lập với các chuỗi dài 15-30 lượt.

---

## 5. Khóa Tập Đánh Giá Mới Holdout v3 (Chưa Chạy Model)

Để kiểm chứng câu hỏi khoa học cốt lõi: *"Liệu recurrent state của DUSN-X có mang lại giá trị độc lập khi bóc tách khỏi SQLite memory và rules hay không?"*, tập `holdout_v3` đã được thiết kế và khóa độc lập:

- **Đặc điểm tập dữ liệu:**
  - **Số lượng:** 20 chuỗi hoàn toàn độc lập, tổng cộng **311 sự kiện** (trung bình 15–18 lượt/chuỗi).
  - **Đặc trưng thiết kế:**
    - Chuỗi dài 15–30 lượt với nhiều phiên làm việc (multi-session).
    - Chuyển đổi qua lại giữa Web ↔ PowerPoint.
    - Hai trí nhớ cùng loại hoạt động đồng thời (2 active databases, 2 active brokers).
    - Sở thích thay đổi theo thời gian và phiên làm việc.
    - Quyết định được xác nhận, từ chối, và tin đồn chưa xác nhận.
    - Câu thiếu chủ ngữ tiếng Việt tự nhiên và câu hỏi không lặp từ khóa với trí nhớ cần dùng (zero-keyword reasoning).
  - **Tách bạch 100% (Zero Overlap):** Đã kiểm tra không trùng lặp người dùng, chuỗi, template hay nội dung với `train`, `validation`, `pilot`, `holdout_v1`, và `holdout_v2`.
- **Mã băm toàn vẹn (Integrity Lock):**
  - File benchmark: `benchmarks/holdout_v3.jsonl`
  - SHA-256: `094268aaf47fa5328786846aff46ebe2f271fd05e2633e681fee472adc8e71bd`
  - Manifest khóa: `benchmarks/holdout_v3.manifest.json`
- **Gói thẩm định mù (Blind Review Package):**
  - `runtime/reviewer_package/holdout_v3_blind_template.csv` (311 dòng).
  - `runtime/reviewer_package/holdout_v3_blind_template.jsonl`.
- **QUY TẮC BẢO TOÀN TRUNG THỰC:**
  - **TUYỆT ĐỐI KHÔNG CHẠY BẤT KỲ CHECKPOINT, BASELINE, RULE HOẶC PREDICTION NÀO TRÊN HOLDOUT V3** trong vòng này.
  - Holdout v3 chỉ được mở để đánh giá khi nhãn được người độc lập thẩm định xong, cấu hình huấn luyện được chốt và có lệnh đánh giá cuối cùng.

---

## 6. Quy Trình Thẩm Định Nhãn Độc Lập & Adjudication

- **Công cụ:** `python/scripts/review_labels.py` & `python/src/dusnx_core/review.py`.
- **Cơ chế chống rò rỉ:** File blind template đã ẩn hoàn toàn nhãn gold và bị chặn tự động nếu truyền vào lệnh so sánh nhãn.
- **Quy trình PowerShell:**
  1. Gửi file `runtime/reviewer_package/holdout_v2_blind_template.csv` hoặc `holdout_v3_blind_template.csv` cho Reviewer 2.
  2. Reviewer hoàn tất gán nhãn, chuyển đổi CSV về JSONL:
     ```powershell
     python python/scripts/review_labels.py --input runtime/reviewer_b_completed.csv --output runtime/reviewer_b.jsonl --from-csv
     ```
  3. Kiểm tra tính hợp lệ của bài nộp:
     ```powershell
     python python/scripts/review_labels.py --input runtime/reviewer_b.jsonl --validate
     ```
  4. So sánh với file Gold chuẩn được giữ kín (xuất Cohen's Kappa và trích xuất danh sách bất đồng):
     ```powershell
     python python/scripts/review_labels.py --input runtime/reviewer_b.jsonl --gold benchmarks/holdout_v2.jsonl --output runtime/agreement_report.json
     ```
  5. Phân xử (Adjudication) chính thức với danh tính người duyệt thật:
     ```powershell
     python python/scripts/review_labels.py --input runtime/reviewer_b.jsonl --gold benchmarks/holdout_v2.jsonl --adjudicate --adjudicator "TenNguoiDuyet" --output runtime/adjudicated_report.json
     ```
  - *Lưu ý:* Các lần chạy thử nghiệm với dữ liệu giả định được đánh dấu rõ `test_only_synthetic_adjudication` và không được báo cáo là đánh giá của con người.

---

## 7. Trạng Thái Notebook Huấn Luyện Google Colab

- **Notebook:** `notebooks/train_dusnx_colab.ipynb`.
- **Trạng thái thực tế:**
  - Mã nguồn notebook và helper script đã được kiểm tra tính đúng đắn, thứ tự cell và logic thực thi cục bộ qua CPU smoke và resume.
  - **CHƯA CÓ PHIÊN HUẤN LUYỆN GPU THẬT NÀO TRÊN GOOGLE COLAB ĐƯỢC CHẠY.** Chúng tôi ghi rõ điều này để đảm bảo tính trung thực nghiên cứu.
- **Cơ chế sẵn sàng cho người dùng:**
  - Tự động nhận diện GPU/CUDA, nếu không có GPU sẽ thông báo rõ ràng và cho phép chạy CPU smoke.
  - Hỗ trợ lưu trữ toàn bộ checkpoints (`router.pt`, `router.last.pt`), configs, metrics epoch, confusion matrix và báo cáo đánh giá vào Google Drive tại `MyDrive/DUSNX/<RUN_NAME>`.
  - Hỗ trợ khôi phục (Resume) tự động khi Colab ngắt phiên (Preemption/Disconnect).
  - Tích hợp bộ đánh giá 5 nhánh trên `holdout_v2.jsonl`.
