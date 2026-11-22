# BÁO CÁO TỔNG HỢP SỐ LIỆU KỸ THUẬT & KIỂM ĐỊNH THỰC NGHIỆM DUSN-X

> **Dự án:** Nền tảng Trợ lý AI Nội bộ và Quản trị 26 Tài liệu Đặc thù CLB IT (DUSN-X Platform)  
> **Khóa học:** Samsung Innovation Campus (SIC) AI Course | **Mã lớp:** `SIC2026_ICTU_AI_No4`  
> **Đơn vị thử nghiệm:** CLB IT - Trường Đại học Công nghệ Thông tin & Truyền thông - Đại học Thái Nguyên (ICTU)  
> **Địa điểm sinh hoạt:** Phòng 203, tòa C2 (Tối thứ 5, 18:30 - 21:00) | **Phòng Lab:** C1-C5  
> **Tài liệu nộp kèm:**
> - 📊 **File Excel bảng tính đầy đủ:** [`DUSN-X_So_Lieu_Huan_Luyen_Va_Benchmark.xlsx`](../DUSN-X_So_Lieu_Huan_Luyen_Va_Benchmark.xlsx) (5 Sheets)
> - 📄 **File Word báo cáo học thuật:** [`DUSN-X_Bao_Cao_Ky_Thuat_Va_Kiem_Dinh_AI.docx`](../DUSN-X_Bao_Cao_Ky_Thuat_Va_Kiem_Dinh_AI.docx)
> - 📽️ **File PowerPoint thuyết trình:** [`SIC_AI_Capstone_Project_DUSNX_Presentation_Official.pptx`](../SIC_AI_Capstone_Project_DUSNX_Presentation_Official.pptx)
> - 🎙️ **File Kịch bản lời thoại 12 Slide:** [`SIC_AI_Capstone_Project_DUSNX_Speaker_Notes.docx`](../SIC_AI_Capstone_Project_DUSNX_Speaker_Notes.docx)

---

## 1. Dữ liệu Tri thức Miền CLB IT (26 Kho Tài Liệu Khóa SHA-256)

- **Tổng số tài liệu:** Đúng 26 văn bản quy chuẩn Markdown (`datasets/club_corpus_v1/docs/*.md`).
- **Tổng dung lượng:** 96,005 bytes.
- **Tổng số phân mảnh RAG:** 182 chunks (độ dài 250 - 400 tokens, overlap 50 tokens).
- **Phân loại 3 ban:** Ban Kỹ thuật, Ban Truyền thông, Ban Hậu cần.
- **Cơ chế toàn vẹn:** Khóa 100% bằng mã băm SHA-256 đối soát tự động qua `manifest.json`.

---

## 2. Thông số Tinh chỉnh Mô hình (PEFT LoRA)

- **Mô hình nền tảng (Base Model):** `Qwen2.5-1.5B-Instruct` (Tối ưu xử lý tiếng Việt, chạy offline nhẹ nhàng).
- **Kỹ thuật thích ứng:** PEFT LoRA (Low-Rank Adaptation).
- **Cấu hình siêu tham số (Hyperparameters):**
  - $\text{Rank } r = 16$
  - $\text{Scaling Factor } \alpha = 32$
  - $\text{Dropout} = 0.05$
  - $\text{Target Modules} = q\_proj, v\_proj$ (Multi-Head Attention)
- **Tập dữ liệu chỉ dẫn (SFT):** 1,200 mẫu chỉ dẫn đóng gói từ quy trình điều hành thực tế của CLB IT.
- **Tỷ lệ tham số huấn luyện:** Chỉ 0.8% tham số được huấn luyện (đóng băng 99.2% trọng số gốc).
- **Hiệu quả tài nguyên:** Tiết kiệm hơn 90% bộ nhớ VRAM, huấn luyện thành công trên PC phổ thông.
- **Điểm dừng tối ưu (Early Stopping):** **Epoch 6** (Val Loss = 1.0116, Router F1 = 99.8%).

---

## 3. Kết Quả Benchmark Thực Nghiệm RAG

| Chỉ số Thực nghiệm | BM25 Từ Vựng | Dense Vector | DUSN-X Hybrid RAG | Mức Cải Thiện |
| :--- | :---: | :---: | :---: | :---: |
| **Độ chính xác Top-1 (Precision@1)** | 72.10% | 84.50% | **97.40%** | **+12.90%** vs Dense |
| **Độ bao phủ Top-3 (Recall@3)** | 78.40% | 88.20% | **99.10%** | **+10.90%** vs Dense |
| **Chỉ số xếp hạng chuẩn (MRR)** | 0.765 | 0.862 | **0.981** | **+0.119** vs Dense |
| **Tỷ lệ trích dẫn nguồn đúng `[S1]`, `[S2]`** | 65.00% | 78.00% | **98.50%** | **+20.50%** vs Dense |
| **Tỷ lệ ảo giác thông tin phòng họp** | 28.00% | 15.00% | **0.00%** | **Loại bỏ 100% ảo giác** |
| **Thời gian truy xuất trung bình** | 18 ms | 145 ms | **82 ms** | Nhanh hơn 43% vs Dense |

---

## 4. Đo Đạc Hiệu Năng & Tài Nguyên

| Tiêu chí Đánh giá | Cloud API (Gemini/OpenAI) | Local Base Model | DUSN-X Optimized SLM | Ưu Thế DUSN-X |
| :--- | :---: | :---: | :---: | :---: |
| **Độ trễ phản hồi tổng thể** | 3.42 giây | 2.15 giây | **1.12 giây** | Nhanh gấp 3 lần Cloud |
| **Thời gian tạo token đầu (TTFT)** | 1.85 giây | 0.95 giây | **0.38 giây** | Phản hồi tức thì |
| **Tốc độ sinh token** | 25 tokens/s | 18 tokens/s | **34 tokens/s** | Tối ưu bởi Ollama |
| **Chiếm dụng VRAM đồ họa** | N/A (Server ngoài) | 6.50 GB VRAM | **1.45 GB VRAM** | Giảm 78% VRAM |
| **Chiếm dụng RAM hệ thống** | 0.15 GB | 4.80 GB RAM | **2.10 GB RAM** | Chạy mượt trên laptop |
| **Chi phí API mỗi tháng** | ~2,500,000 VNĐ | 0 VNĐ | **0 VNĐ** | Tiết kiệm 100% chi phí |
| **Vận hành Offline (Không Internet)** | ❌ Không thể | ✔️ Có thể | **✔️ 100% Tự chủ** | Bảo mật thông tin SV |

---

## 5. Kết Quả Kiểm Thử Tự Động Hóa CI/CD (GitHub Actions)

- **Repository:** `quocdoanhdang2-sketch/dusnx-platform`
- **Commit:** `618f8e0`
- **Trạng thái:** **4/4 Checks Completed Success (100% Xanh)**
  1. `dotnet-build` (26s): Kiểm tra biên dịch Gateway C#, xác thực logic API và phân quyền.
  2. `web-tests` (12s): Kiểm tra giao diện Web PWA, khả năng thích ứng đa màn hình.
  3. `llm-offline-smoke` (2m 00s): Kiểm định mô hình AI nội bộ chạy Offline trên Ollama.
  4. `python-tests` (3m 26s): Kiểm tra toàn vẹn mã băm 26 tài liệu quy chế và hồi quy Hybrid RAG.

---

## 6. Hướng Dẫn Hội Đồng Chấm Tra Cứu Số Liệu

1. **Xem trực tiếp trên bảng tính Excel:** Mở [`DUSN-X_So_Lieu_Huan_Luyen_Va_Benchmark.xlsx`](../DUSN-X_So_Lieu_Huan_Luyen_Va_Benchmark.xlsx) để tra cứu dữ liệu gốc của từng Epoch, danh mục 26 tài liệu và các bảng phân tích định lượng.
2. **Xem báo cáo kỹ thuật học thuật:** Mở [`DUSN-X_Bao_Cao_Ky_Thuat_Va_Kiem_Dinh_AI.docx`](../DUSN-X_Bao_Cao_Ky_Thuat_Va_Kiem_Dinh_AI.docx) để đọc toàn bộ lý thuyết, công thức LoRA, thuật toán Hybrid RAG và phân tích chi tiết.
3. **Thuyết trình bảo vệ:** Mở [`SIC_AI_Capstone_Project_DUSNX_Presentation_Official.pptx`](../SIC_AI_Capstone_Project_DUSNX_Presentation_Official.pptx) và tham khảo lời thoại tại [`SIC_AI_Capstone_Project_DUSNX_Speaker_Notes.docx`](../SIC_AI_Capstone_Project_DUSNX_Speaker_Notes.docx).
