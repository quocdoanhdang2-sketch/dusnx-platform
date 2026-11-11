# Word Add-in runbook

Task pane dùng Office.js `WordApi 1.1` (nâng lên 1.5 khi cần đọc `changeTrackingMode`), đăng nhập
DUSN-X bằng token opaque chỉ giữ trong RAM, chọn/tạo session, đọc đúng đoạn đang chọn, gửi
`/v1/chat`, hiển thị proposal kèm provenance và chỉ ghi khi người dùng bấm **Apply**. Không gửi
toàn tài liệu, không tự ghi, không fallback sang đoạn khác.

Đã kiểm chứng trên Word Desktop thật ngày 2026-11-06/07 và 2026-11-12 (xem
[evidence](../evidence/word-addin-desktop-20261106/README.md) và
[evidence mới](../evidence/office-desktop-20261112/README.md)): Word 16.0.20527.20150,
task pane nạp từ `https://localhost:3001`, proposal/apply/guard chạy thật.

## 1. Chuẩn bị

1. Gateway chạy và `/health` trả `ok` (mặc định `http://localhost:8080`; harness local dùng 8181).
2. Có tài khoản test trên Gateway. Không dùng tài khoản thật cho kiểm thử.
3. Certificate HTTPS cho `localhost` đã được tin cậy trong store của user hiện tại.
4. Word Desktop có hỗ trợ `WordApi 1.1` (mọi bản Word 2016+ hiện hành).

## 2. Phục vụ task pane qua HTTPS

Office chỉ nạp task pane từ HTTPS. Repo có `word-addin/dev-server.js`: server HTTPS dev dùng chung
cho Word và PowerPoint, chỉ phục vụ allowlist asset (Word task pane, PowerPoint task pane,
`deck-template.pptx`), đồng thời proxy `/v1/*` same-origin tới Gateway loopback. Vì vậy task pane
gọi Gateway bằng đường dẫn tương đối, không cần chèn `window.DUSNX_GATEWAY` vào HTML.

```powershell
$env:WORD_ADDIN_TLS_CERT = "C:\certs\localhost-cert.pem"
$env:WORD_ADDIN_TLS_KEY  = "C:\certs\localhost-key.pem"
$env:WORD_ADDIN_GATEWAY  = "http://127.0.0.1:8181"   # Gateway loopback
$env:WORD_ADDIN_PORT     = "3001"                     # tùy chọn, mặc định 3001
$env:WORD_ADDIN_HOST     = "127.0.0.1"                # tùy chọn
node word-addin/dev-server.js
```

Đặc điểm của server dev:

- Allowlist chỉ gồm `/`, `/word-taskpane.html`, `/word-taskpane.js`, `/taskpane.html`,
  `/taskpane.js`, `/deck-template.pptx`; path khác trả `404` (kể cả `/manifest.xml`).
- Proxy chỉ nhận `GET`/`POST` cho `/v1/*`, Gateway phải là loopback (`127.0.0.1`/`localhost`/`::1`),
  không credential/query/path trong URL đích; body tối đa 64 KiB; timeout 120 s.
- Chỉ chuyển tiếp `Authorization`, `Content-Type`, `Accept`; không forward cookie.
- Asset trả `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `Referrer-Policy` và CSP
  (`connect-src 'self'`, `frame-ancestors` cho Office). Không tắt kiểm tra TLS.

Với production, phục vụ task pane và Gateway cùng một origin HTTPS sau reverse proxy; chỉ đặt
`window.DUSNX_GATEWAY` khi buộc phải khác origin, và khi đó phải cấu hình CORS/cookie phù hợp.
Không đưa token vào URL.

Kiểm tra nhanh:

```bash
curl -I https://localhost:3001/word-taskpane.html
curl -s https://localhost:3001/v1/health
```

## 3. Sideload manifest

1. Đăng ký manifest theo user (không cần admin):

```powershell
$key = "HKCU:\Software\Microsoft\Office\16.0\WEF\Developer"
New-Item -Path $key -Force | Out-Null
New-ItemProperty -Path $key -Name "fa2eca6f-d75f-4381-8c0a-d010bf31aba1" `
  -Value "D:\Projects\dusnx-platform\word-addin\manifest.xml" -PropertyType String -Force
```

2. Khởi động lại Word, mở tài liệu test.
3. Ribbon **Home → Add-ins → Developer Add-ins**; mục **DUSN-X Word Assistant** xuất hiện.
4. Nhấp đúp mục này để mở task pane (một lần nhấp chỉ chọn mục trong flyout).
5. Gỡ sideload:

```powershell
Remove-ItemProperty -Path "HKCU:\Software\Microsoft\Office\16.0\WEF\Developer" `
  -Name "fa2eca6f-d75f-4381-8c0a-d010bf31aba1"
```

## 4. Kịch bản kiểm chứng

Chuẩn bị tài liệu có 3 đoạn: tiêu đề, đoạn đích, đoạn cuối. Chọn riêng đoạn đích.

1. Đăng nhập tài khoản test → trạng thái `Connected`, session list xuất hiện.
2. Chọn/tạo session, đặt instruction, bấm **Create proposal from selected text**.
   Tài liệu **chưa đổi**; task pane hiện proposal + provenance.
3. Kiểm provenance có `response_source: "llm"`, `provider_used`, `model_used`.
4. Bấm **Apply to selected text**: chỉ đoạn đang chọn đổi; đoạn cuối và paragraph break
   được giữ; trạng thái `Proposal applied after confirmation.`; nút Apply khóa lại.
5. Tạo proposal mới, đổi selection sang đoạn khác rồi Apply: phải từ chối
   `Selection or text changed...`, proposal bị xóa, tài liệu không đổi.
6. Logout hoặc đổi session/language giữa lúc request đang chạy: request bị abort, response đến
   muộn không được render thành proposal.
7. Thử chọn vùng rỗng hoặc >4000 ký tự: không có request provider.
8. Đặt **Output = Table** và Apply: bảng native chèn tại con trỏ/vùng chọn; trên build hiện tại
   `Range.insertTable` trả `InvalidArgument` nên add-in dựng HTML đã escape rồi `insertHtml`.
9. Bật **Review > Track Changes** rồi Apply: add-in từ chối, xóa draft và không đổi tài liệu:
   `Track Changes is on. Turn it off ...`.
10. Instruction chứa chuỗi giống API key: bị chặn trước khi gọi provider.
11. Sau Apply, `POST /v1/me/events` ghi sự kiện `apply` (nội dung-free) và sự kiện hiện trong
    Web UI Timeline của đúng tài khoản.

## 5. Model theo từng máy

Model do **AI API của máy đó** chọn lúc khởi động; task pane không hard-code model và mỗi request
không đổi model. Cấu hình bằng biến môi trường trước khi chạy `start-local.ps1` (hoặc trước khi
khởi động AI API):

```powershell
# Ollama (mặc định)
$env:DUSNX_PROVIDER = "ollama"
$env:DUSNX_OLLAMA_URL = "http://127.0.0.1:11434"
# Tự chọn Qwen2.5 theo VRAM của máy (4 GB -> 1.5B, 8 GB -> 7B, 16 GB -> 14B)
# nếu không đặt DUSNX_OLLAMA_MODEL. Muốn ép:
# $env:DUSNX_OLLAMA_MODEL = "qwen2.5:1.5b-instruct"
# $env:DUSNX_MODEL_PROFILE = "low"      # auto | low | mid | high
# $env:DUSNX_MODEL_VRAM_GB = "4"        # CPU-only/Docker/Apple Silicon

# Hoặc OpenAI-compatible
$env:DUSNX_PROVIDER = "openai"
$env:DUSNX_OPENAI_BASE_URL = "https://api.openai.com/v1"
$env:DUSNX_OPENAI_MODEL = "gpt-4o-mini"
$env:DUSNX_OPENAI_API_KEY = "..."   # do operator đặt, không ghi vào repo
```

- Auto chỉ chọn model đã có trên máy (`ollama list`); muốn chất lượng cao hơn thì pull model
  của tier đó rồi restart AI API. Máy khác nhau có thể chạy model khác nhau với cùng bản code.
- Đổi biến môi trường phải **restart AI API**, rồi restart Gateway nếu URL đổi.
- Xác minh đúng máy: `curl http://127.0.0.1:8180/health` → `provider.configured_model`,
  `provider.model_available: true`, và `model_profile` (tier, `vram_gb`, model đã chọn).
- Trong Word, provenance của proposal trả `model_used` thực tế; nếu lệch với cấu hình thì task pane
  đang nối nhầm Gateway/API. Model không có sẵn → provider lỗi, không có proposal (guard chặn).

## 6. Giới hạn đã biết

- Đường text chỉ xử lý **plain text** của selection; bảng đi đường riêng **Output = Table**.
  Ảnh, field, footnote chưa hỗ trợ.
- Bật Track Changes thì Apply bị từ chối (WordApi 1.5); add-in không tạo tracked changes ngoài ý
  người dùng.
- Không tự cuộn/khôi phục selection sau Apply; Undo dùng undo stack gốc của Word.
- Chất lượng nội dung phụ thuộc model. Harness và bằng chứng Desktop dùng
  `qwen2.5:1.5b-instruct`; model nhỏ này viết lại chưa ổn định (có thể thêm bullet hoặc suy diễn
  ngoài đoạn gốc). Đây là giới hạn model, không phải lỗi guard; production nên dùng model lớn hơn
  và vẫn giữ bước review thủ công.
- Telemetry apply gửi qua `/v1/me/events` (platform `word`, nội dung-free); không có batch nhiều
  đoạn và không có undo/redo riêng trong pane.
- Manifest dev không ký; chỉ sideload theo user. Phân phối doanh nghiệp cần AppSource hoặc
  central deployment với manifest đã ký và URL HTTPS ổn định.
- Sideload và task pane chạy được với certificate localhost tin cậy; máy khác cần lặp lại bước
  tin cậy certificate hoặc dùng CA nội bộ.

## 7. Khi lỗi

- `Select text in the document first.` — chưa chọn văn bản hoặc selection rỗng.
- `A measured LLM response with provenance is required...` — provider lỗi/trả memory/template;
  không có proposal, tài liệu không đổi.
- `Proposal does not change the selected text.` — model trả lại nguyên văn; tạo lại với
  instruction khác.
- `Selection or text changed...` — selection/session/token đã đổi sau khi tạo proposal; tạo lại.
- `Office API is unavailable` — Office.js chưa nạp hoặc đang mở ngoài Word; kiểm tra manifest
  và host.
