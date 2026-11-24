# DUSN-X — Trợ lý AI Cá nhân hóa cho CLB IT (ICTU)

> **Capstone Project — Samsung Innovation Campus (SIC) 2026**  
> **Lớp:** `SIC2026_ICTU_AI_No4`  
> **Nhóm thực hiện:** Nhóm 2 — **Ngô Như Quỳnh** & **Đặng Quốc Doanh**  
> **Đơn vị:** CLB IT — Trường Đại học Công nghệ Thông tin và Truyền thông — Đại học Thái Nguyên (**ICTU**)

---

## 1. Giới thiệu bài toán & Giải pháp

**DUSN-X Platform** là hệ thống Trợ lý AI nội bộ kết hợp **RAG (Retrieval-Augmented Generation)**, **LoRA Fine-tuning**, **Bộ định tuyến Neural (Router)** và **Sổ tay Trí nhớ cá nhân** dành riêng cho thành viên **CLB IT — ICTU**.

### Tính năng nổi bật
- **Tra cứu 26 tài liệu chuẩn CLB IT có trích dẫn 100% (`[S1]`, `[S2]`):** Lập chỉ mục toàn bộ 26 tài liệu Markdown chuẩn hóa (khóa toàn vẹn `SHA-256`, 225 phân đoạn chunk) về quy chế, lịch sinh hoạt (Thứ 5 hàng tuần, 18:30–21:00 tại Phòng 203 tòa C2), nội quy phòng **Lab C1-C5**, quỹ CLB, tuyển thành viên, sự kiện IT CodeFest, workshop và ban chuyên môn. Mọi câu trả lời tra cứu đều kèm huy hiệu `[Nguồn 1]` tương tác và thẻ tài liệu gốc.
- **Bảo vệ phạm vi thông minh (Scope Gate — Chống ảo giác):** Chỉ trả lời các nội dung xoay quanh CLB IT và sổ tay cá nhân. Với các câu hỏi ngoài phạm vi CLB (thời tiết, bóng đá, giá vàng, giải trí, nấu ăn, v.v.), hệ thống từ chối lịch sự và điều hướng người dùng quay lại các chủ đề của CLB.
- **Sổ tay cá nhân & Trí nhớ dài hạn (SQLite Memory):** Lưu trữ và cập nhật ghi chú, quyết định, sở thích riêng của từng thành viên, tự động truy hồi đúng ngữ cảnh mà không lẫn giữa các tài khoản.
- **Không gian sinh hoạt số cho CLB IT:** Tích hợp đăng nhập phân quyền (Chủ nhiệm / Trưởng ban / Thành viên), Bảng tin CLB, Kho 26 tài liệu có tìm kiếm, Tin nhắn nội bộ (DM & Nhóm), và chế độ so sánh song song với API ngoài (Gemini).
- **Chạy hoàn toàn Native trên Windows (Không cần Docker):** Nhanh, gọn, bảo mật dữ liệu nội bộ nhờ mô hình cục bộ Ollama (`qwen2.5:1.5b-instruct`).

---

## 2. Kiến trúc hệ thống

```text
Trình duyệt Web (web-ui — PWA)
   │  http://127.0.0.1:8090
   ▼
ASP.NET Core Gateway (.NET 8 — :8090)
   │  Phục vụ Web UI tĩnh + Reverse Proxy /v1/* + Xác thực Bearer Token
   ▼
FastAPI AI API (Python — :8010)
   ├─ Scope Gate & Intent Router (Neural Router + Rule Guards)
   ├─ RAG Engine (SQLite FTS5 + Trigram — 26 tài liệu CLB IT, 225 chunks, SHA-256)
   ├─ Personal Memory & Auth DB (SQLite: auth.db, memory.db)
   └─ LLM Provider: Ollama cục bộ (Qwen2.5 + LoRA) / Dự phòng Gemini API
```

---

## 3. Cấu trúc thư mục dự án

```text
dusnx-platform/
├── datasets/
│   ├── club_corpus_v1/          # Kho 26 tài liệu chuẩn CLB IT (.md) + manifest.json (SHA-256)
│   ├── club_sft_train_v1/       # Dữ liệu huấn luyện SFT/LoRA (train / validation / test JSONL)
│   └── club_sft_v1/             # Bộ kịch bản đánh giá hội thoại CLB IT
├── python/
│   ├── apps/ai_api/             # Backend FastAPI (main.py, rag.py, provider.py, auth.py, memory.py)
│   ├── src/dusnx_core/          # Mô hình Router Neural, pipeline huấn luyện & kiểm định
│   ├── scripts/                 # Script train, build RAG index, benchmark
│   └── tests/                   # Bộ kiểm thử tự động (502 test cases — 100% PASS)
├── gateway-dotnet/              # Cổng Gateway ASP.NET Core (.NET 8)
├── web-ui/                      # Giao diện Web Chat, Kho tài liệu, Bảng tin, Sổ tay cá nhân
├── docs/                        # Tài liệu kiến trúc, quy chế, bằng chứng nghiệm thu club-demo-p0
├── run-servers.py               # Script khởi chạy đồng thời Ollama, FastAPI (:8010) & Gateway (:8090)
├── SIC_AI_Capstone_Project_DUSNX_Presentation_Official.pptx   # Slide thuyết trình chính thức
├── SIC_AI_Capstone_Project_DUSNX_Speaker_Notes.docx           # Kịch bản thuyết trình chi tiết
├── DUSN-X_Bao_Cao_Ky_Thuat_Va_Kiem_Dinh_AI.docx               # Báo cáo kỹ thuật & kiểm định AI
└── DUSN-X_So_Lieu_Huan_Luyen_Va_Benchmark.xlsx                # Bảng số liệu huấn luyện & Benchmark
```

---

## 4. Hướng dẫn cài đặt & Chạy nhanh (Windows)

### Yêu cầu môi trường
- **Python 3.11 – 3.14** (đã cài đặt các thư viện trong `python/pyproject.toml`).
- **.NET 8 SDK** (chạy Gateway ASP.NET Core).
- **Ollama** với model cục bộ:
  ```powershell
  ollama pull qwen2.5:1.5b-instruct
  ```

### Khởi chạy toàn bộ hệ thống (1 lệnh duy nhất)
```powershell
python run-servers.py
```
Sau khi khởi chạy thành công:
- Truy cập giao diện Web UI tại: **`http://127.0.0.1:8090`**
- AI API FastAPI hoạt động tại: **`http://127.0.0.1:8010`**

### Chạy bộ kiểm thử tự động
```powershell
# Tạo lại chỉ mục RAG từ 26 tài liệu CLB IT
$env:PYTHONPATH="python;python/src"
python -m apps.ai_api.rag --rebuild

# Chạy toàn bộ 502 bài kiểm thử tự động
pytest python/tests
```

---

## 5. Tài liệu bàn giao & Nghiệm thu

| Tài liệu | Mô tả |
| :--- | :--- |
| `SIC_AI_Capstone_Project_DUSNX_Presentation_Official.pptx` | Bộ slide thuyết trình Capstone chuẩn Samsung Innovation Campus |
| `SIC_AI_Capstone_Project_DUSNX_Speaker_Notes.docx` | Kịch bản thuyết trình chi tiết từng slide cho Nhóm 2 |
| `DUSN-X_Bao_Cao_Ky_Thuat_Va_Kiem_Dinh_AI.docx` | Báo cáo kỹ thuật kiến trúc, huấn luyện LoRA, RAG & kiểm định |
| `DUSN-X_So_Lieu_Huan_Luyen_Va_Benchmark.xlsx` | Bảng số liệu Loss, Accuracy, F1 Score và kết quả Benchmark |
| `docs/evidence/club-demo-p0/ACCEPTANCE-2026-11-20.md` | Biên bản nghiệm thu tính năng CLB IT |
