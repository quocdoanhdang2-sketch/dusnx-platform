# Hướng Dẫn Huấn Luyện DUSN-X Trên Google Colab Từng Bước

Notebook huấn luyện: [train_dusnx_colab.ipynb](../notebooks/train_dusnx_colab.ipynb).
*Trạng thái xác minh: Mã nguồn notebook và helper scripts đã được kiểm tra tính đúng đắn, không lỗi import, thứ tự cell và logic thực thi cục bộ qua CPU smoke. Chưa có phiên huấn luyện GPU thật nào trên Google Colab được chạy — tài liệu này hướng dẫn người dùng chạy thật.*

> **Phạm vi huấn luyện:** Đây là quá trình huấn luyện mạng cập nhật trạng thái động (recurrent state updater cell) và 3 đầu phân loại routing (intent, agent, next_action). Tuyệt đối **không fine-tune Large Language Model (LLM)**. Cơ chế lưu trữ, xác nhận, phủ định và khử thông tin lỗi thời trong trí nhớ vẫn do SQLite CRUD và active-memory grounding đảm nhiệm.

---

## 5 Bước Thao Tác Cụ Thể Trên Google Colab

### Bước 1: Mở Notebook và Chọn Runtime GPU
1. Mở trình duyệt web, truy cập: **https://colab.research.google.com**.
2. Chọn **File → Upload notebook** → duyệt và tải lên file [notebooks/train_dusnx_colab.ipynb](../notebooks/train_dusnx_colab.ipynb) (hoặc chọn tab **GitHub**, dán URL repository `https://github.com/quocdoanhdang2-sketch/dusnx-platform` và chọn file).
3. Bấm **File → Save a copy in Drive** để lưu bản sao vào Google Drive cá nhân của bạn.
4. Trên thanh menu Colab, chọn:
   **Runtime → Change runtime type** (hoặc *Thời lượng chạy → Thay đổi loại phần cứng*).
   - **Hardware accelerator:** Chọn **GPU** (T4, V100 hoặc A100 tùy tài khoản Colab cấp).
   - Bấm **Save**.
5. Bấm nút **Connect** ở góc trên bên phải để kết nối máy ảo.

### Bước 2: Mount Google Drive và Cấu Hình Thư Mục Lưu Trữ
1. Chạy **Cell 1 & 2** (Environment setup & Drive mount). Colab sẽ hiển thị hộp thoại pop-up:
   - Bấm **Connect to Google Drive** (hoặc *Kết nối với Google Drive*).
   - Chọn tài khoản Google của bạn và bấm **Allow** (Cho phép).
2. Notebook sẽ tự động tạo thư mục đầu ra tại:
   `/content/drive/MyDrive/DUSNX/<RUN_NAME>` (mặc định ví dụ `colab_run_001`).
3. Toàn bộ checkpoint (`router.pt`, `router.last.pt`), manifest băm dữ liệu, lịch sử training từng epoch (`epochs.jsonl`), báo cáo đánh giá (`summary.json`, `summary.md`, `cases.json`, `errors.json`) sẽ được ghi trực tiếp vào Google Drive này. Bạn sẽ không bị mất dữ liệu khi phiên Colab kết thúc.

### Bước 3: Chuẩn Bị Dữ Liệu và Kiểm Tra Không Rò Rỉ
1. Chạy **Cell 3 & 4** (Clone repo, cài đặt dependencies và prepare data).
2. Script `prepare_data.py` tự động:
   - Tổng hợp 24 họ kịch bản đa lượt tiếng Việt (`designed_data.py`) với các chuỗi clarification, correction, và các cặp đối lập phụ thuộc recurrent state.
   - Trích lọc an toàn 100 sequence từ tập synthetic legacy.
   - **Bảo toàn chống rò rỉ (Leakage Prevention):** Tách bạch 100% không gian chuỗi giữa Train (371 chuỗi, 4,185 sự kiện; 596 mẫu `clarify`) và Validation (46 chuỗi, 203 sự kiện; 38 mẫu `clarify`).
   - Loại trừ tuyệt đối các chuỗi thuộc `benchmarks/holdout_v1.jsonl`, `benchmarks/holdout_v2.jsonl` và `benchmarks/holdout_v3.jsonl`.
3. *Về Hugging Face Token (nếu muốn tải nguồn gated như CSConDa sau khi được cấp quyền):*
   - Tuyệt đối **không dán token vào notebook hoặc khung chat**.
   - Mở biểu tượng **Secrets** (hình chiếc chìa khóa ở thanh công cụ bên trái Colab).
   - Thêm secret mới: Name: `HF_TOKEN`, Value: `<token_cua_ban>`.
   - Bật công tắc **Notebook access**.
   - CSConDa hiện chưa được cấp quyền nên pipeline mặc định tự động bỏ qua an toàn mà không làm gián đoạn huấn luyện.

### Bước 4: Chạy Huấn Luyện (Training) và Cơ Chế Tự Khôi Phục (Resume)
1. Trong cell cấu hình:
   - Đặt `SMOKE = False` để chạy huấn luyện GPU đầy đủ theo `configs/router_colab.yaml` (8 epochs, batch size 32, gradient accumulation 2, mixed precision FP16).
   - Nếu Colab không cấp GPU hoặc chỉ muốn kiểm tra nhanh luồng trong 2-3 phút, giữ `SMOKE = True` (chạy CPU smoke).
2. Bấm chạy cell Huấn Luyện:
   - Đầu ra in rõ: Commit SHA thực tế, Python version, PyTorch version, tên GPU và VRAM khả dụng.
   - Mỗi epoch in train/val loss và macro-F1 của intent, agent, action.
   - Checkpoint tốt nhất được lưu tự động thành `router.pt`.
   - Trạng thái phiên chạy (optimizer, scaler, learning rate scheduler, random seed state) được lưu atomic thành `router.last.pt` sau mỗi epoch.
3. **Cách nhận biết huấn luyện hoàn tất:**
   - Dòng log cuối cùng thông báo: `Huấn luyện thành công. Checkpoint tốt nhất: .../router.pt`.
   - Trong Google Drive `MyDrive/DUSNX/<RUN_NAME>/` xuất hiện đầy đủ các file:
     - `router.pt` (checkpoint tốt nhất tính theo validation macro-F1).
     - `router.last.pt` (checkpoint epoch cuối cùng).
     - `config.yaml` / `router.config.json` (toàn bộ siêu tham số, commit SHA và cấu trúc mô hình).
     - `router.epochs.jsonl` (lịch sử metric chi tiết của từng epoch).
     - `router.metrics.json` (tổng kết loss và macro-F1).
4. **Cách khôi phục khi Colab bị ngắt đột ngột (Preempted / Disconnected):**
   - Kết nối lại runtime mới, mount Drive cũ.
   - Đặt `RESUME = True` trong notebook, giữ nguyên `RUN_NAME` cũ.
   - Pipeline sẽ tải `router.last.pt`, khôi phục chính xác epoch, optimizer, scaler, RNG state và tiếp tục huấn luyện mà không cần chạy lại từ đầu.

### Bước 5: Đánh Giá 5 Nhánh Độc Lập Trên Holdout v2 và Tải Kết Quả
1. Chạy cell Đánh Giá (Evaluation cell):
   - Chạy tự động đánh giá tách biệt 5 nhánh (`--all-systems --include-model-only`) trên tập khóa `benchmarks/holdout_v2.jsonl` (38 bước, 10 chuỗi):
     1. `baseline_a`: Không trí nhớ (No-memory, thuần rule routing).
     2. `baseline_b`: Trí nhớ tĩnh (Static-memory, append-only, rule routing).
     3. `model_only`: Checkpoint mô hình thuần túy (không qua rule override, không qua active-memory grounding).
     4. `dusnx_no_state`: Nhánh ablation (xóa sạch recurrent state ẩn sau mỗi bước, giữ nguyên SQLite CRUD và rules).
     5. `dusnx`: Hệ thống đầy đủ (recurrent state + SQLite CRUD + rules/grounding).
   - In bảng so sánh trực quan kèm khoảng tin cậy Wilson 95% CI.
   - *Lưu ý quan trọng:* Tập `holdout_v3.jsonl` (311 bước, 20 chuỗi dài) đã được khóa độc lập nhưng **tuyệt đối KHÔNG được đánh giá trong lượt này** cho đến khi có thẩm định độc lập và chốt model cuối cùng.
2. Tải kết quả về máy cục bộ:
   - Vào Google Drive cá nhân, mở thư mục `MyDrive/DUSNX/<RUN_NAME>/`.
   - Nhấp chuột phải vào thư mục → Chọn **Download** (Tải xuống).
   - Giải nén vào thư mục `artifacts/<RUN_NAME>/` trên máy cục bộ để đối chiếu hoặc tích hợp vào Gateway/Web chatbot.

---

## Hướng Dẫn Quy Trình Thẩm Định Nhãn Độc Lập (Human Review Workflow)

Để bảo đảm tính trung thực nghiên cứu, tập nhãn `holdout_v2`, `holdout_v3` và dữ liệu synthetic tuyệt đối không được tự ý ghi `human_reviewed=true` khi chưa có người thật kiểm tra.

### File gửi cho người duyệt (Reviewer 2)
- Gửi file: `runtime/reviewer_package/holdout_v2_blind_template.csv` hoặc `runtime/reviewer_package/holdout_v3_blind_template.csv`.
- *Lưu ý:* File này là **Blind Template**, đã ẩn hoàn toàn nhãn AI, đáp án và dự đoán của mô hình để người duyệt không bị thiên kiến. Tuyệt đối không dùng file blind làm gold trong lệnh đối soát.

### Các cột người duyệt cần điền trong file CSV:
1. `label_intent`: Chọn trong 6 nhãn (`chat`, `research`, `summarize`, `presentation_edit`, `recommendation`, `followup`) hoặc nhãn đặc thù memory (`memory_create`, `decision_modify_intent`, `decision_update`, `decision_update_cancelled`).
2. `label_agent`: Chọn trong 3 agent (`conversation`, `search_rag`, `productivity`) hoặc `memory`.
3. `label_action`: Chọn (`reply`, `search`, `summarize`, `edit_slide`, `recommend`, `clarify`, `create_memory`, `await_confirm`, `update_memory`, `no_op`).
4. `label_requires_clarification`: Điền `true` nếu câu nói mơ hồ, thiếu tham số cần hỏi lại; điền `false` nếu rõ ràng.
5. `label_active` / `label_obsolete`: Điền thông tin sự thật còn hiệu lực hoặc đã lỗi thời.
6. `notes`: Ghi chú lý do nếu câu hỏi có bẫy (như phủ định, đổi ý, tin đồn chưa xác nhận).

### Các lệnh PowerShell thực hiện sau khi nhận lại file:
```powershell
$env:PYTHONPATH="python/src;python"

# 1. Chuyển đổi CSV người duyệt gửi về định dạng JSONL chuẩn
python python/scripts/review_labels.py --input runtime/reviewer_b_completed.csv --output runtime/reviewer_b.jsonl --from-csv

# 2. Kiểm tra tính hợp lệ về định dạng và danh mục nhãn
python python/scripts/review_labels.py --input runtime/reviewer_b.jsonl --validate

# 3. So sánh với file Gold chuẩn được giữ kín (tính Cohen's Kappa và trích xuất danh sách bất đồng)
python python/scripts/review_labels.py --input runtime/reviewer_b.jsonl --gold benchmarks/holdout_v2.jsonl --output runtime/agreement_report.json

# 4. Xuất bản phân xử (Adjudication) chính thức với danh tính người duyệt thật
python python/scripts/review_labels.py --input runtime/reviewer_b.jsonl --gold benchmarks/holdout_v2.jsonl --adjudicate --adjudicator "TenNguoiDuyet" --output runtime/adjudicated_report.json
```

---

## Các Lệnh Chạy Cục Bộ (Local Equivalent Commands)

Nếu bạn muốn chạy thử nghiệm trên máy tính Windows cá nhân:

```powershell
# Thiết lập môi trường Python
$env:PYTHONPATH='python/src;python;.;scripts'

# 1. Kiểm tra smoke test toàn bộ pipeline huấn luyện (epoch, atomic save, resume)
python python/scripts/pipeline_smoke.py --output runtime/my-smoke-run

# 2. Chuẩn bị dữ liệu huấn luyện mới nhất
python python/scripts/prepare_data.py --legacy data/synthetic_30k_v2.jsonl

# 3. Chạy huấn luyện CPU smoke test (2-3 phút)
python python/scripts/train.py --config configs/router_colab.yaml --device cpu --smoke --epochs 2 --checkpoint artifacts/router_local_test.pt

# 4. Thử nghiệm cơ chế khôi phục từ checkpoint dở dang
python python/scripts/train.py --config configs/router_colab.yaml --device cpu --smoke --epochs 4 --checkpoint artifacts/router_local_test.pt --resume artifacts/router_local_test.last.pt

# 5. Chạy đánh giá 5 nhánh độc lập trên holdout v2
python python/scripts/evaluate_personalization.py --benchmark benchmarks/holdout_v2.jsonl --holdout-manifest benchmarks/holdout_v2.manifest.json --all-systems --include-model-only --provider mock --output-dir runtime/eval_holdout_v2
```
