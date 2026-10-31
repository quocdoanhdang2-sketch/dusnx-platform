# Bàn giao lộ trình DUSN-X — 31/10/2026

## Baseline và phạm vi thực tế

- Repo: quocdoanhdang2-sketch/dusnx-platform, checkout `/workspace/dusnx-platform`.
  Phiên cloud **không truy cập** `D:\Projects\dusnx-platform`. Patch chưa được áp
  vào máy Windows; không khẳng định checkout này chứa các sửa đổi Windows mới nhất.
- Branch `work`, HEAD `121d946752f46579d2f231b372afd3ec2d76f6ef`, status/diff ban đầu
  rỗng. Baseline lưu `/workspace/scratch/dusnx-roadmap-baseline.json`. Không có file
  người dùng đang sửa trong checkout này. Không tìm thấy AGENTS.md áp dụng; đã đọc
  README, architecture, runbook Windows/PowerPoint, data gates, training runbook và
  runtime skill; dùng lại harness Week 4. Không có executor skill bổ sung.
- Ban đầu không có Gateway/FastAPI/Ollama đang chạy. Harness tạo process và DB tổng
  hợp riêng, rồi stop đúng child handle; cuối đợt không để dịch vụ ứng dụng chạy.
- Ở lượt triển khai ban đầu chưa commit/push/PR/deploy; không reset/clean/rebase/chép đè checkout hoặc dữ liệu
  có sẵn. Không đổi cấu trúc bảng, service boundary hoặc model production.

## Trạng thái từng giai đoạn

| Giai đoạn | Trạng thái | Bằng chứng và giới hạn |
|---|---|---|
| 1. Dữ liệu v2 | ĐÃ XÁC MINH một phần / CHỜ NGƯỜI THẬT | 100 train + 24 validation, hash/schema đạt; 124 needs_human_review; similarity train–validation max 0.7782 < 0.82. Gói Windows chỉ định không có trong cloud; test/receipt độc lập chưa xác minh. |
| 2. Training/evaluation | CHƯA ĐẠT GATE | Không training, prediction test, mở Holdout hoặc promote. Không GPU/Ollama/checkpoint production ở instance này. |
| 3. Memory | ĐÃ SỬA / ĐÃ XÁC MINH RUNTIME | Active/supersede/user/project/provenance/version/update/delete/clarify, retry, write failure và recovery. Ngữ cảnh dài kiểm harness vì không có LLM thật. |
| 4. Web/PowerPoint | Web ĐÃ XÁC MINH RUNTIME; PPT ĐÃ SỬA, HARNESS | Chromium thật đăng ký/tự login, session/chat, lưu/recall, provenance, provider/mạng lỗi. API thật kiểm login/project/health. Office mock xác minh guard, HTTPS/CORS local thật; chưa Desktop/WebView Windows. |
| 5. Mở rộng | ĐÃ KIỂM KÊ / THIẾT KẾ, CHƯA TÍCH HỢP | Chưa Word/Teams/image-edit provider. Zalo normalized skeleton, chưa OA. Không gửi tin hoặc tạo UI giả. |
| 6. Vận hành | ĐÃ SỬA / XÁC MINH MỘT PHẦN | Auth hash, rollback DB, JSON 503, request limits, localhost guard, webhook fail-closed, backup/restore và fault processes. Retention/purge/production readiness còn thiếu. |

Không đọc `benchmarks/holdout_v3.jsonl` hoặc `test_draft.jsonl` trong đợt này.
Không chạy bộ test training/SFT/benchmark có thể chạm dữ liệu đang khóa. Số kiểm thử
bên dưới là bộ ứng dụng được chọn, không phải toàn bộ suite.

## File đã thay đổi và lý do

| File | Thay đổi |
|---|---|
| python/apps/ai_api/memory.py | Thêm cửa sổ tin gần nhất, giữ API phân trang cũ; version history theo superseded_by thay vì timestamp; rollback khi tạo memory thất bại. |
| python/apps/ai_api/main.py | Dùng cửa sổ gần nhất cho context/retry; SQLite error trả JSON 503 an toàn, không coi write thất bại là success. |
| python/apps/ai_api/auth.py | Scrypt có version, nâng cấp SHA-256 cũ sau login đúng; rollback đăng ký lỗi; không đổi cột/table hoặc reset tài khoản. |
| gateway-dotnet/Program.cs | State/events legacy thêm guard loopback/Origin; webhook thiếu secret trả 503; bodyless logout không bị 415. |
| docker-compose.yml | Cho Host nội bộ ai-api trong allowlist; không cấp secret Zalo mẫu mặc định. |
| powerpoint-addin/taskpane.js | Đúng một selected shape; snapshot slide/shape/text/session; proposal/provenance/unchanged guard; không Apply nhầm; bỏ kết quả async sau logout. |
| powerpoint-addin/manifest.xml | PowerPointApi 1.5 cần cho getSelectedShapes; chưa xác minh support trên Office máy người dùng. |
| powerpoint-addin/taskpane.html | Nhãn đúng shape, chỉ Apply nội dung đã review; mặc định yêu cầu rewrite text không kèm giải thích. |
| powerpoint-addin/taskpane.test.js | Kiểm thử Office mock cho proposal/Apply, đổi mục tiêu/text, metadata/empty/unchanged, logout khi đang chờ. |
| powerpoint-addin/README.md; docs/POWERPOINT_ADDIN_RUNBOOK.md | Sửa mô tả polling cũ, hướng dẫn guard và việc Desktop còn cần người dùng xác minh. |
| .github/workflows/ci.yml | Thêm chạy kiểm thử PowerPoint mock; chưa push nên chưa có CI remote mới. |
| python/tests/test_memory_reliability.py | Regression context dài/retry, version trùng timestamp, migration auth cũ. |
| scripts/verify_memory_reliability.py | HTTP/Chromium/SQLite thật trên DB mới; reuse Stack/API Week 4; đóng đúng process sở hữu. |
| docs/LLM_V2_GATE_NEXT.md | Số liệu mới, cột cần người thật, nguồn v2/khác biệt gói Windows và thứ tự gate. |
| docs/PLATFORM_INTEGRATION_STATUS.md | Kiểm kê Word/Teams/Zalo/image và checklist tích hợp tối thiểu. |
| docs/OPERATIONS_RELIABILITY.md | Backup/restore, fault behavior, retention/xóa còn thiếu, access/health/log/artifact limits. |
| docs/ROADMAP_20261031_HANDOFF.md | Báo cáo này. |

Package/evidence mới ở `runtime/roadmap-20261031/`, được ignore:
gate_status.json, train-validation-review/{review.csv,review.md,review_manifest.json},
train-validation-review.zip, runtime process evidence và HTTPS check. Không điền
decision/reviewer/reviewed_at/reason/revised_answer. Không sửa dữ liệu SFT hoặc manifest
gốc. ZIP chỉ có package chưa duyệt và README_NEXT, không có test bị khóa/credential.

## Kiểm chứng thực chạy

1. Bộ 11 file kiểm thử ứng dụng: **109 passed**, 12.68s, không skip. Lệnh trong
   `/workspace/scratch/dusnx-roadmap-tests-handoff.log`; bộ test được chạy với
   PYTHONPATH=python/src:python/apps:python:.:scripts, OMP_NUM_THREADS=2:
   `python/.venv/bin/python -m pytest` cùng các file:
   test_memory_reliability, test_http_integration, test_week1_acceptance,
   test_week2_acceptance, test_memory_quality, test_memory_grounding,
   test_chat_provenance, test_week4_integration, test_post_week4_i18n,
   test_takeover_regressions, test_state_compatibility (trong python/tests, hậu tố .py),
   `-q --tb=short`. Đây là harness, không phải inference chất lượng LLM thật.
2. `node web-ui/app.test.js`: **11/11**; `node powerpoint-addin/taskpane.test.js`:
   **9/9**, Office mock. .NET Release build **0 warnings/errors**, Gateway history
   `dotnet run --project gateway-dotnet.tests/Dusnx.Gateway.Tests.csproj -c Release`:
   **7/7**. Manifest XML/Compose YAML static parse đạt, không build/run Docker.
3. `python/.venv/bin/python scripts/verify_memory_reliability.py --output-dir
   runtime/roadmap-20261031/runtime-final-02`: **10 nhóm runtime đạt**, exit 0.
   Có Gateway/.NET + FastAPI + SQLite + Chromium thật, provider URL port trống;
   không fake Ollama thành LLM thật. Kết quả `runtime-final-02/report.json`.
4. HTTPS taskpane tại URL manifest `https://localhost:3001/taskpane.html` được phục
   vụ và kiểm bằng CA cục bộ có xác minh TLS; OPTIONS qua Gateway chấp nhận origin
   đó; Host ai-api được nhận, Host lạ bị 400. `https-check/report.json`.
   Không cài cert vào trust store và không chạy PowerPoint Desktop.
5. Các lượt đầu **có thất bại**, được giữ nguyên: runtime-01 phát hiện bodyless
   logout 415 và kiểm thử reuse connection sau 413; runtime-02 phát hiện SQLite
   write fault giữ transaction; runtime-final phát hiện upstream connection sau
   exception có thể dẫn đến 503 ở write tiếp theo. Đã chẩn đoán/sửa rồi chạy lại,
   không xóa báo cáo thất bại hoặc đổi nhãn thành pass.
6. Git diff review/diff --check đạt; HEAD/branch không đổi. Baseline sạch nên không
   có thay đổi người dùng bị mất. Không tuyên bố CI remote hoặc Windows đã chạy.

## Lỗi/giới hạn còn lại

- Checkout Windows và gói gate chỉ định chưa được đồng bộ/xác minh; không chép patch
  đè các guard hoặc dữ liệu mới trên máy đó. Cần so sánh đúng baseline trước áp dụng.
- Toàn bộ gate LLM v2 chưa đạt; chưa có generation thật hoặc so sánh base/candidate.
  Giữ base, không đủ bằng chứng promote. Similarity chưa có test trong phạm vi đo.
- PowerPoint Desktop, Office requirement support, trusted HTTPS và shape thật cần
  người dùng nghiệm thu. Mock pass không chứng minh Desktop pass.
- Chat giữ global DB lock qua lời gọi provider; throughput nhiều user bị tuần tự.
  Chưa thay concurrency design trong patch này.
- Jobs/presentations/SignalR legacy, proxy-IP rate limiting và liveness chưa kiểm DB
  vẫn cần production hardening. Không public toàn bộ route chỉ vì test local đạt.
- Web mở lại phiên hiện tải trang mặc định 100 tin; chưa có UI phân trang đầy đủ.
- Chưa có retention/purge-account hoàn chỉnh; DELETE memory là soft-delete, version/
  chat/receipt/backup có thể giữ nội dung. Không xóa dữ liệu thật trong tác vụ này.

## Chính xác việc người dùng cần làm

1. Giữ nguyên `D:\Projects\dusnx-platform` và gói
   `runtime/llm-v2-human-gate-20261005-114208`; đồng bộ/đối chiếu code và gate package
   trước áp patch cloud. Không dùng reset/clean hoặc thay thế cả runtime.
2. Theo docs/LLM_V2_GATE_NEXT.md: 124 dòng review, các cột decision/reviewer/reviewed_at;
   revise cần revised_answer/reason và contract hợp lệ. Dùng gói Windows nếu đó là
   bản nguồn mới hơn; package cloud ZIP chỉ là bản chưa duyệt ở baseline này.
3. Người thật viết 6–12 test độc lập, người khác duyệt trước prediction. Chạy validator/
   exact tokenizer/receipt/attestation/lock đúng nguồn rồi mới xét Colab training.
4. Trên Windows có Ollama/checkpoint tin cậy, chạy stack và kiểm generation/provenance
   thật; sideload PowerPoint manifest, chọn Text Box, Create proposal → review → Apply,
   thử đổi slide/shape/text theo runbook. Không gửi secret vào chat.
5. Nếu mở Word/Teams/Zalo/image: chọn integration/provider và cung cấp quyền/credential
   qua secret store, không source. Chốt retention/xóa và production owner trước public.

Kết luận: **mức demo phát triển có kiểm chứng local**, đã sửa các lỗi độ tin cậy và
bổ sung guard. **Chưa đạt candidate-v2 evaluation và chưa production-ready**.

## Bổ sung: review trước push theo yêu cầu tiếp theo

Người dùng đã cho phép commit/push sau khi review và kiểm thử. Đích bàn giao là nhánh
`fix/memory-office-reliability`, xuất phát từ `121d946`; không merge main, tạo PR hay deploy.
Đã review lại diff auth/SQLite/Gateway/Office, làm sạch định dạng các khối try Office
và bỏ import không dùng của harness. Không mở gate dữ liệu hoặc thay model.

Kiểm tra trước commit ngày 31/10/2026: Python 109 passed (12.86s), Web 11/11,
PowerPoint Office mock 9/9, Gateway 7/7, .NET Release 0 warning/error; harness HTTP/
Chromium thực `runtime/prepush-review-20261031/report.json`: 10/10 nhóm đạt.
Đây là kiểm chứng local. Nhánh fix không khớp push trigger main/develop/feature/*
của workflow hiện tại; không kích hoạt CI training smoke khi gate còn đóng và
không tuyên bố remote CI đã chạy. Evidence, DB, backup, review CSV và TLS key dưới
runtime/ được giữ ngoài commit. Cần xác minh remote HEAD sau push mới kết luận
đã đưa bản commit lên GitHub.
