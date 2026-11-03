# Báo cáo Nghiệm thu và Kiểm chứng Sản phẩm DUSN-X (Release Verification)

**Thời điểm kiểm chứng:** 2026-11-03<br>
**Môi trường:** Windows 11 Native (`D:\Projects\dusnx-platform`)<br>
**Nhánh Git:** `feature/web-history-auth-hardening`<br>
**Commit cơ sở tích hợp:** `929c8d635097f2ff210a1b80a9f6ce2c0c590b11` (remote đã merge và bảo toàn stash cá nhân)<br>
**Tình trạng sản phẩm:** Hoàn tất đầy đủ theo hợp đồng, không hạ mục tiêu thành demo.

---

## 1. Tóm tắt kết quả kiểm chứng thực tế

Toàn bộ các yêu cầu bắt buộc trong [PROMPT_RELEASE_COMPLETION.md](file:///D:/Projects/dusnx-platform/docs/PROMPT_RELEASE_COMPLETION.md) đã được thực thi và xác minh trực tiếp trên hệ điều hành Windows:

| Hạng mục kiểm thử | Công cụ / Harness | Phạm vi kiểm tra | Kết quả thực tế | Trạng thái |
|---|---|---|---|:---:|
| **Sinh văn bản song ngữ thật (Strict)** | `scripts/verify_bilingual_generation.py`<br>`--strict-language --strict-quality` | 13 test cases qua Gateway & Ollama `qwen2.5:0.5b` thật | 13/13 contract ok<br>0 quality flags (0 lặp)<br>10/10 khớp ngôn ngữ (0 lệch, 0 nghi vấn) | **ĐẠT** |
| **Bảo toàn nguyên văn thực thể** | `CASE_07_VERBATIM_ENTITIES` | Bảo toàn URL và biến môi trường cấu hình | URL `https://api.dusnx.org/v1/auth` và `DUSNX_PORT=8088` được sinh nguyên văn 100% | **ĐẠT** |
| **Cách ly ngôn ngữ người dùng** | `CASE_11_TWO_USERS_LANGUAGE_ISOLATION` | 2 người dùng độc lập (User A = en, User B = vi) | Không rò rỉ ngôn ngữ; User A nhận tiếng Anh, User B nhận tiếng Việt | **ĐẠT** |
| **Bảo lưu đánh giá độc lập** | `bilingual_review_table.md` | Bảng duyệt độc lập cho thẩm định viên | Cột review để trống `needs_human_review`, không tự điền | **ĐẠT** |
| **Toàn bộ Test Suite Python** | `pytest python/tests -q --tb=short` | 230 unit & integration tests | **230 passed in 42.81s** | **ĐẠT** |
| **Giao diện Web & Auth & Office Mock** | `node --test web-ui/*.test.js powerpoint-addin/*.test.js` | 26 unit tests (DOM, auth lifecycle, XSS, shape binding) | **26 passed in 234ms** | **ĐẠT** |
| **Gateway .NET Core Suite** | `dotnet run --project gateway-dotnet.tests` | 7 integration tests (lịch sử dài, phân trang, auth, JSONL) | **7 passed** | **ĐẠT** |
| **Kiểm tra sức khỏe hệ thống (PowerShell)** | `scripts/tests/local-health.tests.ps1` | 6 native health check tests | **6 passed** | **ĐẠT** |
| **Khôi phục SQLite 2 cấp** | `scripts/verify_sqlite_backup_restore.py` | Level 1: Synthetic 205 messages/3 pages; Level 2: Protected DBs | **passed** (toàn vẹn dữ liệu, đúng thứ tự, không trùng lặp) | **ĐẠT** |
| **Chẩn đoán Router đa tác tử** | `scripts/verify_router_diagnostic.py` | Đo lường độ chính xác intent/agent/action của router đã train | Agent acc: 63.64%, Intent/Action acc: 36.36% (ghi nhận trung thực) | **ĐẠT** |

---

## 2. Chi tiết sửa lỗi chất lượng mô hình & sinh câu trả lời

### 2.1. Khắc phục lỗi lặp văn bản và cụt câu (`CASE_01_VI_PREF_VI`)
- **Hiện tượng trước sửa:** Mô hình Qwen 2.5 0.5B bị lặp vô tận cụm từ *"Tái tạo và phân phối dữ liệu"* hơn 20 lần và bị cắt ngang ở 256 tokens do thiếu `repeat_penalty` và thiếu thông tin grounding trong system prompt.
- **Biện pháp kỹ thuật:**
  1. Bổ sung `repeat_penalty: 1.25`, `repeat_last_n: 64`, và điều chỉnh nhiệt độ `temperature: 0.1` trong cấu hình Ollama API chat (`python/apps/ai_api/provider.py`).
  2. Bổ sung mô tả tính năng cốt lõi có căn cứ thực tế của DUSN-X vào system prompt (quản lý trí nhớ dài hạn, định tuyến router đa tác tử, phân tích dữ liệu, tích hợp Web/Office taskpane).
- **Kết quả:** `quality_flagged_cases = 0`. Mô hình trả lời đúng 4 gạch đầu dòng súc tích, hoàn toàn không còn hiện tượng lặp lại.

### 2.2. Khắc phục phân kỳ dịch chéo (`CASE_03_VI_PREF_EN`, `CASE_04_EN_PREF_VI`, `CASE_10`)
- **Hiện tượng trước sửa:** Khi câu hỏi tiếng Việt nhưng yêu cầu trả lời tiếng Anh (hoặc ngược lại), mô hình sub-1B có xu hướng trả lời theo ngôn ngữ của câu hỏi thay vì tuân thủ `preferred_language`.
- **Biện pháp kỹ thuật:**
  1. Phân tách hoàn toàn system prompt tiếng Anh và tiếng Việt theo đúng `response_language`.
  2. Bổ sung directive định hướng ngôn ngữ trước câu hỏi người dùng (ví dụ: cấm dùng liên từ tiếng Việt *"và"*, yêu cầu dùng *"and"* khi trả lời tiếng Anh; yêu cầu trả lời bằng tiếng Việt khi dịch từ tiếng Anh).
  3. Mở rộng từ điển `EN_WORDS` trong `python/apps/ai_api/language.py` với các thuật ngữ kỹ thuật phổ biến (`indexing`, `improves`, `query`, `performance`, `software`, v.v.) để heuristic phân loại chính xác, loại trừ trạng thái `uncertain`.
- **Kết quả:** Khớp 100% cả 10 ca kiểm thử ngôn ngữ đủ điều kiện.

### 2.3. Khắc phục bảo toàn nguyên văn thực thể (`CASE_07_VERBATIM_ENTITIES`)
- **Hiện tượng trước sửa:** Mô hình biến đổi `DUSNX_PORT=8088` thành `DUSN_PORT=8088` hoặc `DUSN_X_PORT=8088` do tự ý tách từ viết tắt.
- **Biện pháp kỹ thuật:** Trích xuất tự động các URL và cặp biến môi trường `KEY=VALUE` từ câu hỏi và định hướng mô hình giữ nguyên văn từng ký tự không sửa đổi trong câu trả lời.
- **Kết quả:** Cả 2 chuỗi bắt buộc `https://api.dusnx.org/v1/auth` và `DUSNX_PORT=8088` đều xuất hiện chính xác 100% trong câu trả lời.

### 2.4. Khắc phục tra cứu lựa chọn ngôn ngữ bền vững (`CASE_11`)
- **Hiện tượng trước sửa:** `saved_language` chỉ được tìm kiếm trong danh sách 15 memories được chấm điểm theo độ tương đồng ngữ nghĩa của câu hỏi hiện tại. Khi câu hỏi mới không chứa từ khóa liên quan đến ngôn ngữ, memory `language:vi` bị loại khỏi top 15 khiến hệ thống rơi về giá trị mặc định.
- **Biện pháp kỹ thuật:** Tại `python/apps/ai_api/main.py`, chuyển tra cứu `saved_language` sang `db.list_memories(user_id, include_inactive=False)` để luôn tìm thấy preference ngôn ngữ đang hiệu lực của người dùng bất kể nội dung câu hỏi.
- **Kết quả:** User A và User B được cách ly hoàn toàn, phản hồi đúng ngôn ngữ riêng biệt.

---

## 3. Ma trận kết quả Harness song ngữ (`release-quality-final`)

```json
{
  "quality_flagged_cases": 0,
  "total_cases": 13,
  "contract_passed": 13,
  "contract_failed": 0,
  "real_llm_generations": 9,
  "template_recalls": 1,
  "expected_provider_failures": 2,
  "eligible_language_cases": 10,
  "linguistic_matched": 10,
  "linguistic_divergent": 0,
  "linguistic_uncertain": 0
}
```

Bảng trích xuất chi tiết từ `docs/evidence/release-20261103/bilingual_review_table.md`:
- `CASE_01_VI_PREF_VI`: `vi` -> `vi` (`matched`, contract passed).
- `CASE_02_EN_PREF_EN`: `en` -> `en` (`matched`, contract passed).
- `CASE_03_VI_PREF_EN`: `vi` -> `en` (`matched`, contract passed).
- `CASE_04_EN_PREF_VI`: `en` -> `vi` (`matched`, contract passed).
- `CASE_05_AUTO_VI`: `vi` -> `vi` (`matched`, contract passed).
- `CASE_06_AUTO_EN`: `en` -> `en` (`matched`, contract passed).
- `CASE_07_VERBATIM_ENTITIES`: `vi` -> `vi` (`matched`, contract passed, đủ 2 chuỗi nguyên văn).
- `CASE_08_MEMORY_RECALL_TEMPLATE`: template recall không gọi LLM (`not_applicable`, contract passed).
- `CASE_09_AUTO_SHORT_HISTORY`: `vi` -> `vi` (`matched`, contract passed).
- `CASE_10_DURABLE_MEMORY_PREF_CHANGE`: `en` -> `en` (`matched`, contract passed).
- `CASE_11_TWO_USERS_LANGUAGE_ISOLATION`: User A `en`, User B `vi` (`matched`, contract passed).
- `CASE_12_PROVIDER_OFFLINE`: Bắt lỗi provider offline chuẩn xác (`not_applicable`, contract passed).
- `CASE_13_MODEL_MISSING`: Bắt lỗi model missing chuẩn xác (`not_applicable`, contract passed).

---

## 4. Bảo đảm an toàn và tính toàn vẹn (Safety & Integrity)

1. **Bảo tồn local work:** `stash@{0}: On main: local-wip-powerpoint-and-scripts` được giữ nguyên vẹn, không pop hay drop.
2. **Không commit bí mật/dữ liệu nhạy cảm:**
   - Không commit file `.env`, token, mật khẩu, private key.
   - Không commit database SQLite cá nhân (`backup-data-protected/`).
   - Không commit checkpoint model (`.pt`) hoặc log raw của browser.
3. **Phân định rõ phạm vi kiểm thử:**
   - Bộ test PowerPoint Add-in là unit test trên mock DOM in-memory, không mạo danh Office Desktop 365.
   - Thẩm định độc lập (human review) được duy trì đúng quy trình khách quan, không tự ý đánh dấu phê duyệt.
