# Kiến trúc hệ thống — Chatbot cá nhân hoá cho câu lạc bộ

> Trạng thái: BẢN THIẾT KẾ & HỒ SƠ HOÀN THIỆN ĐÀO TẠO.
> Tác giả hệ thống & dữ liệu: **Doanh** | Người thẩm định chất lượng: **Quỳnh**.
> Ngày cập nhật: 2026-11-17. Nhánh làm việc: `club-assistant` (giữ nguyên không push main).

## 1. Tên gọi và tâm đề bài

**"Hệ thống chatbot cá nhân hoá cho câu lạc bộ"** — nhấn mạnh chữ *cá nhân hoá* ở mọi tài liệu,
vì đó là tên đề bài. CLB chỉ là môi trường áp dụng; cái được chấm là cá nhân hoá.

Một câu tóm tắt: **mọi thành viên CLB dùng chung một chatbot, nhưng mỗi người có một trợ lý khác nhau.**

## 2. Thang cá nhân hoá 4 tầng (khung xuyên suốt báo cáo + demo)

| Tầng | Bot làm gì | Cơ chế |
|---|---|---|
| 1. Nhận diện | Gọi tên, xưng hô theo vai trò, giao diện theo vai trò | `users.role` + `club_profile.yaml` |
| 2. Nhớ riêng | Sổ tay cá nhân: vai trò, deadline, sở thích; hỏi lại trước khi ghi | `memory.db` + `pending_decision_updates` |
| 3. Theo phong cách riêng | Ngắn gọn/đầy đủ tùy ngườii; nhắc việc riêng của từng ngườii | sở thích trong sổ tay + tóm tắt phiên cũ (`chat_summaries`) |
| 4. Học từ tương tác | Ngườii dùng sửa bot → bot đổi ngay → lượt sửa vào đợt train lại | `session_signal` (correction) + review queue + retrain |

## 3. Kiến trúc tổng thể

```
Điện thoại (PWA)          Máy tính (trình duyệt)
      \                        /
       \                      /
        Web UI (web-ui, rebrand CLB, responsive, PWA)
                    │ HTTP
                    ▼
        Gateway ASP.NET Core :8080 (auth, rate limit 120/phút/IP, body 1 MiB)
                    │ loopback
                    ▼
        AI API FastAPI :8000
          ├── Cổng phạm vi CLB (TF-IDF cosine, ngưỡng ~0.095 — hiệu chỉnh lại trên corpus CLB)
          ├── RAG kho CLB (SQLite FTS5, corpus khóa hash)
          ├── Trợ lý cá nhân (memory.db: sổ tay, pending xác nhận, tóm tắt phiên)
          ├── Não chính: MODEL TỰ TRAIN (Qwen2.5-0.5B + LoRA, qua Ollama/llama.cpp)
          └── Dự phòng: Gemini API (chỉ khi model chính lỗi; hiện tag "trả lờii dự phòng")
                    │
        Dữ liệu: auth.db (users/tokens/roles) · memory.db · club corpus + index · member_messages
```

Nguyên tắc não chính/phụ: **model tự train trả lờii mọi câu hỏi; Gemini chỉ đứng sau khi model lỗi
hoặc khi ngườii dùng bấm "So với API".** Gemini không còn trong luồng chính.

## 4. Luồng xử lý một câu hỏi

```
Câu hỏi vào
  │
  ▼
Bước 1 — Cổng phạm vi CLB
  ├── NGOÀI phạm vi → MODEL TỰ TRAIN từ chối lịch sự + gợi ý câu hỏi đúng chủ đề
  └── TRONG phạm vi → bước 2
        ▼
Bước 2 — Tìm kho tài liệu (RAG). Không gọi Gemini.
  ├── KHÔNG có tài liệu → "Kho tài liệu CLB chưa có nội dung này, liên hệ quản lý" (không bịa)
  └── CÓ tài liệu → bước 3
        ▼
Bước 3 — MODEL TỰ TRAIN đọc đoạn tài liệu + sổ tay cá nhân ngườii hỏi
         → viết câu trả lờii + trích nguồn (học từ dữ liệu train)
  │
  └── (nếu model lỗi) → Gemini trả lờii thay, tag "trả lờii dự phòng"
```

Chống bịa bằng kiến trúc: câu trả lờii kiến thức bắt buộc đi từ RAG; không có tài liệu thì
không được trả lờii. Dữ liệu train dạy *cư xử*, kho RAG cung cấp *kiến thức*.

## 5. Vai trò và phân quyền

Bốn tầng vai trò, hiện badge màu ở mọi nơi (danh sách thành viên, đầu tin nhắn):

| Vai trò | Badge | Quyền |
|---|---|---|
| Chủ CLB | cam "Chủ CLB" | Toàn quyền: duyệt dữ liệu train, khóa + nạp kho, quản lý thành viên, ghim thông báo |
| Phó CLB | cam nhạt "Phó CLB" | Thêm văn bản vào kho, quản lý thành viên, xem thống kê |
| Trưởng ban | tím "Trưởng ban" | Tạo nhóm chat cho ban mình, ghim tin trong nhóm ban |
| Thành viên | xanh "Thành viên" | Chat AI, nhắn tin, sổ tay, xem tài liệu |

- Một mã nguồn web duy nhất; vai trò quyết định màn hình/nút nào hiện sau đăng nhập.
- Đăng ký tự do → **quản lý duyệt** mới được chat. Tài khoản quản lý đầu tiên cấp bằng lệnh.
- Migration: thêm cột `role` vào bảng `users` (auth.db), không mất dữ liệu cũ.

## 6. Màn hình (6 tab, tab cuối chỉ vai trò quản lý thấy)

1. **Chat AI** (màn mở đầu): streaming; gợi ý câu hỏi *theo vai trò/ngườii dùng*; thẻ trích nguồn
   bấm được; câu ngoài phạm vi hiện khung đỏ nhẹ + gợi ý đúng chủ đề; bot hỏi lại khi ghi nhớ
   (nút "Đúng, ghi nhớ / Không"); nút 👍👎 + ô "sai chỗ nào"; nút "So với API"; nút "Chạy demo".
   Đầu tab: bảng tin 3–4 thông báo ghim (chủ/phó CLB đăng).
2. **Tin nhắn**: danh sách thành viên kèm badge vai trò → nhắn 1-1 (hỏi chủ CLB, phó CLB trực tiếp);
   nhóm theo ban + nhóm "Toàn CLB"; ghim thông báo; polling vài giây (không cần WebSocket).
3. **Kho tài liệu**: danh sách văn bản, tìm kiếm, xem trước, tải về; dấu "đã khóa hash"; quản lý có
   nút "Thêm văn bản".
4. **Sổ tay của tôi**: xem/sửa/xóa điều bot nhớ về mình, bot hỏi xác nhận trước khi đổi.
5. **Quản lý** (chủ/phó): thành viên (thêm/xóa/đổi vai trò/duyệt đăng ký); kho tài liệu
   (thêm → khóa hash → nạp, 2 nút); duyệt dữ liệu train (giữ/sửa/loại từng cặp); thống kê
   (câu hỏi theo tuần, tỉ lệ trong/ngoài phạm vi, tỉ lệ 👍).
6. **Hồ sơ / Cài đặt**: đổi mật khẩu, sáng/tối, phong cách trả lờii (ngắn gọn/đầy đủ), đăng xuất.

Onboarding lần đầu: bot chủ động hỏi 2–3 câu (phụ trách mảng nào, thích trả lờii kiểu gì) → ghi sổ tay.

## 7. Dữ liệu train (600–800 cặp, 3 tầng nguồn)

| Tầng | Nguồn | Số lượng | Ghi chú |
|---|---|---|---|
| 1. Thật | Phiên chat thật (hiện có 181 phiên) sau khi ngườii duyệt | ~390 | Hành vi thật |
| 2. Trích từ kho CLB | Mỗi văn bản → 20–25 biến thể câu hỏi; câu trả lờii **copy nguyên văn từ tài liệu** + nguồn | ~350–450 | Không thể bịa; soát nhanh |
| 3. Nháp API (nếu cần nối) | Gemini diễn đạt lại câu hỏi | ~50–100 | Duyệt tay toàn bộ |

- Mỗi cặp gắn nhãn nguồn (real/extractive/gemini-drafted); tỉ lệ nêu trong báo cáo.
- Thêm: cặp multi-turn (2–3 lượt); ~100 cặp câu hỏi ngoài phạm vi ↔ từ chối đúng format;
  cặp ghi nhớ (hỏi lại xác nhận).
- Quy chế: `docs/TRAINING_POLICY.md` (có sẵn) — con ngườii duyệt trước khi train; test set đóng băng;
  hyperparams cố định trong `configs/llm_sft.yaml`; gate trước khi dùng.
- Train/validation chia theo phiên. Đo trước/sau train trên cùng test set → bảng so sánh trong báo cáo.

## 8. Kho tài liệu và khóa hash

- **Hồ sơ CLB: tên "CLB IT"** — ghi trong `club_profile.yaml`; toàn bộ văn bản, tên thành viên,
  tên ban đều mang tính chất CLB IT (ban kỹ thuật, ban truyền thông...).
- Corpus CLB giả lập 16–20 văn bản, **toàn dữ liệu fictitious** (không PII thật), sinh từ
  `club_profile.yaml` (tên CLB, loại hình, ban, thành viên — đổi CLB nhảy/tiếng Anh... chỉ sửa 1 file).
- Khóa hash: manifest SHA-256 theo file (cơ chế `domain_corpus.py` có sẵn); file đổi 1 chữ → check báo lỗi.
- Index SQLite FTS5 riêng (`runtime/club-rag/`), không đè `rag.db` của DUSN-X.
- Thêm mới: thành viên thả file → quản lý chạy 2 lệnh (khóa lại + nạp). Không tự động ghi đè kho.

## 9. Tin nhắn nội bộ

- Bảng mới `member_messages` (không dùng chung bảng chat AI); 1-1 và nhóm theo ban.
- API: danh sách thành viên, gửi/nhận, tạo nhóm (trưởng ban). Polling vài giây.
- Vai trò hiện badge; chủ/phó ghim tin nhóm "Toàn CLB".

## 10. Vòng lặp cải tiến (khép yêu cầu "huấn luyện lại")

👍👎 + lượt sửa → `session_signal` phân loại (correction) → review queue → đợt train lại
(theo 4 trigger trong TRAINING_POLICY). Đây là minh chứng "quy trình đào tạo" bằng sản phẩm.

## 11. Kế hoạch triển khai

1. Nhánh `club-assistant` + corpus CLB + khóa hash + index + test set (1 buổi).
2. Vai trò 4 tầng + duyệt đăng ký (migration auth).
3. Rebrand web: 6 tab, responsive, PWA (manifest + service worker).
4. Pipeline: model tự train chính / Gemini dự phòng + nút "So với API".
5. Tin nhắn nội bộ + nhóm theo ban.
6. Sinh dữ liệu train 3 tầng → duyệt → train (1–2h chạy) → gate → nạp model vào app.
7. Test toàn bộ + demo máy tính + điện thoại (cùng WiFi).

## 12. Rủi ro và đường về

- **Chất lượng câu trả lờii model 0.5B thấp hơn Gemini** — chấp nhận được; demo chọn câu hỏi
  ngắn, thuộc tài liệu rõ. Nút "So với API" biến điểm yếu thành phần trình bày trung thực.
- **Quota Gemini** — model train + RAG đã là đường chính, dự phòng thêm lớp.
- **181 phiên thật là của 1 ngườii** — tầng 2 bù; ghi nhãn rõ trong báo cáo.
- **Rollback:** `git checkout main` là về nguyên bản; database CLB nằm file riêng.
- **Mọi lần restart AI API / đổi cấu hình chạy thật đều cần đồng ý riêng của chủ dự án.**

## 13. Ngoài phạm vi (nói trước để khỏi hỏi)

App native riêng; video call; push notification qua FCM; đa CLB đồng thởi; đồng bộ Office add-in.
Các mục này để phần "hướng phát triển" trong báo cáo.
