# Nghiệm thu Tuần 2 — bằng chứng thực chạy

Ngày kiểm chứng: 2026-09-28. HEAD lúc tiếp quản:
`84312337604e2fdda039f6ed6f4ca6d66fe7e50c`, kèm thay đổi chưa commit trên ổ đĩa.
Không sử dụng báo cáo phiên trước làm bằng chứng mới.

## Trạng thái

**Đạt kịch bản PostgreSQL → xác nhận MongoDB → hỏi lại ở phiên mới**, cả HTTP
qua Gateway và trình duyệt Chromium thật. Đây là nghiệm thu cục bộ cho kịch bản
cụ thể, không phải tuyên bố mọi câu trả lời hay mọi nhãn routing đều đúng.

| Bằng chứng | Thời gian UTC | Kết quả |
|---|---|---|
| HTTP thật `scripts/verify_real_ollama_week2.py` | 2026-09-28 16:06:21 | Tất cả 8 điều kiện đạt |
| UI thật `scripts/verify_web_week2.py` | 2026-09-28 16:11:20 | Đăng ký, logout/login bằng form, 4 lượt chat, phiên mới, xem trí nhớ đạt |

Các artifact đã lọc thông tin xác thực nằm trong [evidence/week2](evidence/week2/).
HTTP report ghi method/path/status, không ghi request body đăng nhập hoặc headers.
UI report ghi kiểm tra DOM và HTTP qua Gateway; ảnh `chat.png` và `memory.png`
được chụp từ giao diện thật bằng tài khoản kiểm thử riêng. Không dùng TestClient
để chứng minh Web/Gateway.

Câu trả lời thực nhận: **“Cơ sở dữ liệu của dự án này hiện tại là MongoDB.”**
`provider_ok=true`, `provider_used=ollama`; MongoDB đang active và được đưa vào
prompt, PostgreSQL đã inactive và không có trong `memory_ids_used`. Phiên hỏi
lại có ID khác phiên tạo/sửa. HTTP client PowerPoint mô phỏng gửi event tiếp theo:
state version từ 4 lên 5, timeline chứa Web và PowerPoint.

`model_used=qwen2.5:0.5b` và `tokens_generated=15` trong lần chạy HTTP này lấy từ
`model` và `eval_count` do Ollama `/api/chat` trả về. Đây là token sinh câu trả lời
của Ollama, không phải token/checkpoint routing DUSN-X. Nếu provider không trả số
đo thì API trả null, script không in giá trị suy đoán; mock không báo số token.

## Kiến trúc đối chiếu code

- Web `:8080` → Gateway ASP.NET Core **HttpClient proxy** → FastAPI `:8000`
  → Ollama `:11434`. Repo chưa dùng YARP.
- Gateway `/health` chỉ là liveness của Gateway. Web đọc **`/v1/health`** để
  hiển thị trạng thái checkpoint/provider; lỗi gọi nhầm `/health` đã được sửa.
- Auth dùng **opaque Bearer token**, lưu trong bảng SQLite `tokens`; không phải
  JWT. Web giữ token trong bộ nhớ và `sessionStorage`, xóa khi logout.
- PostgreSQL/MongoDB ở kịch bản là **nội dung quyết định được nhớ**, không phải
  database vật lý của hệ thống. Auth, memory, state và events vẫn lưu SQLite.
- `/v1/me/state` và `/v1/me/events` lấy danh tính từ token. `/api/v1/history/...`
  cũ vẫn là endpoint quan sát development, chỉ loopback mặc định.
- PowerPoint là HTTP client mô phỏng, chưa chứng minh Office Add-in thực tế.
- Checkpoint routing hiện tại: `dusnx_smoke_v2.pt`, model version
  `checkpoint:dusnx_smoke_v2.pt:sha256-c1e898a0e483:config-03b14389ce98`.
  Luật xử lý ghi nhớ/xác nhận và Ollama sinh câu trả lời là các phần riêng.

## Chạy lại

Từ thư mục gốc, dùng Python môi trường dự án (máy kiểm chứng có
`python/.venv/Scripts/python.exe`):

```powershell
$env:PYTHONPATH="python/src;python;.;scripts"
.\start-local.ps1
python scripts/verify_real_ollama_week2.py --output runtime/week2-http.json
python -m pip install playwright
python -m playwright install chromium
python scripts/verify_web_week2.py --output-dir runtime/week2-ui
```

Nếu Chromium đã có, truyền `--browser-executable <đường-dẫn-chrome>`; đường dẫn máy
kiểm chứng không phải yêu cầu dự án. Dùng `DUSNX_PROVIDER=ollama`, model đã được
cài tại Ollama; CPU được hỗ trợ, không yêu cầu GPU cụ thể.

Script tạo tài khoản kiểm thử riêng, không đọc dữ liệu người dùng sẵn có và
không ghi token/mật khẩu. Dịch vụ/provider lỗi hoặc thiếu điều kiện → exit 1,
`status=unverified` (“chưa kiểm chứng”), giữ lỗi trong report. Script HTTP không
tự đánh dấu UI đạt. Cần chạy cả hai lệnh để khép hai loại bằng chứng.

## Test và giới hạn

Python tests kiểm tra cô lập người dùng/project, state/event transaction,
dedup/retry, xác nhận/từ chối, ambiguity, provider failure và regression mới.
Web tests kiểm tra XSS và endpoint health; kiểm thử trình duyệt còn bắt lỗi CSS
khi `hidden` không ẩn chỉ báo “Đang xử lý”. Kết quả đầy đủ và lệnh kiểm tra được
ghi trong [WEEK3_PILOT.md](WEEK3_PILOT.md).

Lượt HTTP trước đó tại `runtime/week2-http.json` báo chưa kiểm chứng vì script
chưa yêu cầu `include_inactive=true`, nên không thấy bản PostgreSQL cũ. Script đã
được sửa và chạy lại; không coi sự vắng mặt trong danh sách active là bằng chứng
đã supersede. Báo cáo cũ chứa thông tin cài đặt/GPU/UI chưa đối chiếu đã được
thay bằng bằng chứng trên; bản nháp tiếp quản giữ cục bộ trong `runtime/takeover/`.
