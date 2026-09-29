# Train DUSN-X trên Google Colab từng bước

Notebook: [train_dusnx_colab.ipynb](../notebooks/train_dusnx_colab.ipynb). Đã kiểm tra helper/smoke trên máy local; **chưa tuyên bố chạy Colab**. Đây là train state updater dạng recurrent và intent/agent/action router, không fine-tune LLM. Memory create/confirm/supersede vẫn là luật và SQLite.

1. Mở https://colab.research.google.com → **File → Upload notebook** → chọn file trên. Hoặc tab GitHub, dán URL repository rồi chọn notebook. Bấm **Save a copy in Drive**.
2. Bấm **Runtime → Change runtime type → Python 3 → Hardware accelerator GPU → Save** nếu train lớn. GPU khả dụng tùy Colab; không yêu cầu model GPU cụ thể. Giữ `SMOKE=True` để chạy CPU smoke khi không có GPU. [Colab FAQ](https://research.google.com/colaboratory/faq.html) giải thích giới hạn tài nguyên.
3. Chạy ô clone/cài đặt bằng nút tam giác. Nếu project đã mở, sửa `PROJECT` về đúng thư mục. `REVISION` nên là commit đã duyệt; ô in HEAD thực chạy. Python phải từ 3.11 đến 3.13; dependency lấy từ `python/pyproject.toml` qua `pip install -e './python[dev,data]'`. Ô tiếp in Python, PyTorch và GPU thực tế.
4. Chạy ô Drive → **Connect to Google Drive** → chọn tài khoản → cấp quyền. Chọn `RUN_NAME` mới để không ghi đè checkpoint. Checkpoint, config, hash/seed/labels, metric epoch và optimizer/RNG resume được lưu trong `MyDrive/DUSNX/<RUN_NAME>`.
5. Smoke không tải dataset. Train lớn (`SMOKE=False`) tải MASSIVE và hai file SGD tham khảo theo revision cố định. CSConDa mặc định bỏ qua: chỉ truy cập trang HF, chấp nhận điều kiện và chờ cấp quyền. Nếu được duyệt, mở biểu tượng chìa khóa **Secrets**, tạo `HF_TOKEN`, bật Notebook access; lấy bằng `google.colab.userdata.get('HF_TOKEN')` vào `os.environ`, không in. Gọi `fetch_sources.py --source csconda --allow-gated`. Không cần CSConDa để train các nguồn còn lại.
6. Nếu muốn dùng 30k cũ, tải `synthetic_30k_v2.jsonl` local lên `MyDrive/DUSNX/input/`. Để so mốc 23aaa48, tải checkpoint `dusnx_smoke_v2.pt` cũ lên cùng thư mục. Checkpoint không ở git; helper đối chiếu SHA-256. Thiếu file sẽ báo thiếu baseline, không tự dựng điểm cũ. Không dùng token trong URL clone hoặc notebook.
7. Chạy ô prepare: xem số nhận/loại, nguồn, chuỗi, phân bố label và tỷ lệ lặp. MASSIVE chưa duyệt mapping bị loại khỏi train. Không đưa pilot/holdout vào train. Xuất mẫu bằng `review_labels.py` và giao reviewer theo [hướng dẫn](ANNOTATION_GUIDE.md). Hiện nhãn synthetic chưa duyệt độc lập, nên đây là thử nghiệm pilot.
8. Chạy ô train. Smoke dùng model nhỏ 2 epoch và thực sự kiểm tra resume. Train lớn dùng `configs/router_colab.yaml`, lựa batch theo VRAM còn trống, gradient accumulation=2, mixed precision CUDA, early stopping patience=3. Dòng epoch in train/validation macro-F1; **không dùng holdout để chọn best**. `router.pt` là best; `router.last.pt` có optimizer/scaler/RNG để resume.
9. Nếu runtime bị ngắt: mount lại Drive, dựng lại cùng dữ liệu/config, đặt `RESUME=True`, giữ đường dẫn cũ rồi chạy train. Hash data/config phải khớp. Nếu OOM, giảm batch ở config và bắt đầu run mới (hoặc quay lại cấu hình cũ để resume); không che giấu thay đổi cấu hình. Không có GPU thì dùng smoke hoặc dừng train lớn với thông báo rõ.
10. Chạy ô đánh giá: 3 chế độ cũ + ablation reset recurrent state mỗi event. SQL memory/lịch sử và luật giữ nguyên ở ablation. Notebook mặc định `mock`: kiểm tra pipeline/routing, **không đánh giá được LLM final answer**. Muốn số đầy đủ, tải checkpoint về máy local có Ollama rồi dùng lệnh dưới. Kết quả chứa prediction từng bước, case, summary, errors và attribution model/rule.
11. Bấm phải thư mục run trong Google Drive → **Download**. Giải nén trên Windows vào `artifacts/<RUN_NAME>/`. Không commit `.pt`, raw data, token, DB hoặc log riêng tư.

## Lệnh local tương đương

PowerShell, dùng venv Python 3.11–3.13 của repo (máy hiện tại dùng `python/.venv/Scripts/python.exe`):

```powershell
$env:PYTHONPATH='python/src;python;.;scripts'
python python/scripts/pipeline_smoke.py --output runtime/my-new-smoke
python python/scripts/prepare_data.py --legacy data/synthetic_30k_v2.jsonl
python python/scripts/train.py --config configs/router_colab.yaml --checkpoint artifacts/my-run.pt
# CPU thử nghiệm giới hạn, không phải train GPU Colab:
python python/scripts/train.py --config configs/router_colab.yaml --device cpu --smoke --epochs 3 --init-from artifacts/dusnx_smoke_v2.pt --checkpoint artifacts/my-cpu-run.pt
# Resume cùng data/config/device:
python python/scripts/train.py --config configs/router_colab.yaml --checkpoint artifacts/my-run.pt --resume artifacts/my-run.last.pt --epochs 12
python python/scripts/evaluate_personalization.py --benchmark benchmarks/holdout_v1.jsonl --holdout-manifest benchmarks/holdout_v1.manifest.json --include-no-state --provider ollama --checkpoint artifacts/my-run.pt --output-dir runtime/my-evaluation
```

Chạy Ollama service và bảo đảm `ollama list` có `qwen2.5:0.5b` (hoặc đặt `DUSNX_OLLAMA_MODEL` về tag đã cài). Lỗi kết nối/provider sẽ giữ output đã chạy và exit khác 0; không đổi thành kết quả đạt. Notebook chạy eval qua FastAPI TestClient, không chứng minh Web/Gateway; bằng chứng HTTP/UI Tuần 2 dùng script riêng trong README.

Lỗi thường gặp: `ModuleNotFoundError` → chạy đúng ô cài pip và PYTHONPATH; gate 401/403 → chờ chủ dataset duyệt, không thử lách; checkpoint đã tồn tại → dùng resume hoặc tên run mới; resume hash mismatch → khôi phục đúng data/config cũ; CUDA unavailable → chọn GPU hoặc CPU smoke; Drive đầy → đổi thư mục/dọn file của chính bạn. Dataset license/revision và giới hạn ở [DATA_SOURCES](DATA_SOURCES.md).
