# Tuần 4 — nghiệm thu và bàn giao

Ngày nghiệm thu: 2026-10-04 (Asia/Saigon). Trạng thái: native/Web đạt; Git/CI đang chốt.
HEAD trước: `e5dac2c890301b0c6c976f3c169244851df110c6`.
HEAD sau implementation: sẽ ghi khi commit; SHA cuối của commit bàn giao không thể
nằm trong chính nội dung commit đó, xác định bằng `git rev-parse HEAD` và CI đúng SHA.
Thay đổi có sẵn `scripts/import_llm_ollama.ps1` được bảo toàn và loại khỏi commit này.

## Nguồn và kiến trúc

Đối chiếu README, ARCHITECTURE, WEEK1/2_ACCEPTANCE, WEEK3_PILOT,
WEEK3_HANDOFF, CHECKPOINT_COLAB_RUN_01 và WEEK3_LLM_TRAINING.
Không tìm thấy `DUSNX_KIEN_TRUC_VA_HUONG_DI.md` hoặc kế hoạch acceptance Tuần 4
riêng trong repo/nhánh hiện hành. Bảng dưới dùng acceptance đã có và yêu cầu Tuần 4
của người dùng; không suy diễn Office Add-in thành yêu cầu native đã triển khai.

Web hiện có → Gateway ASP.NET Core HttpClient proxy → FastAPI → router PyTorch,
state vector và memory SQLite → Ollama. Auth là opaque Bearer token, không phải JWT.
Legacy Gateway có JSON state/job queue cho demo Phase 1, tách khỏi state SQLite
có xác thực. PowerPoint Add-in/Zalo là skeleton; Web platform là mô phỏng input.
Router tự train không sinh văn bản. CRUD/xác nhận/template là code ứng dụng.
LoRA Qwen là pipeline sinh văn bản riêng; base vẫn `qwen2.5:0.5b`.

## Acceptance matrix

| ID | Yêu cầu | Trạng thái hiện tại | Việc cần làm | Cách kiểm chứng | Bằng chứng | Kết quả |
|---|---|---|---|---|---|---|
| W4-01 P0 | Checkpoint thật, state tương thích | Hash khớp, trained_dusnx, state schema rõ | Đã root-resolve và khai báo source/model | SHA + native health + RT-15 + state invalid | evidence/week4/runtime.json | đạt |
| W4-02 P0 | Startup/proxy/provider trung thực | Identity/source/binary kiểm đúng, cổng cấu hình | Đã sửa, không kill owner khác | RT-10/11/14/16 + stop/restart thật | evidence/week4/runtime.json | đạt |
| W4-03 P0 | Auth/cách ly user | Foreign API404, token invalid/revoked/expired401 | TTL seconds đã sửa đúng | RT-09/12 + Web401 | runtime.json, browser.json | đạt |
| W4-04 P0 | Memory/supersede/retry | API/DB khớp, supersede version2, reject giữ nguyên | PUT chặn inactive, receipt bền | RT-02/03/04/08 + SQLite + direct_update | runtime.json; regression tests | đạt |
| W4-05 P1 | Recall/clarification/provenance | Hai topic chọn đúng, ambiguous hỏi lại | Replay không giả gọi provider | RT-05/06/07 + llm_replay | runtime.json | đạt |
| W4-06 P1 | Web auth/chat/history/cards/UX/XSS | Chromium thật, mobile390px, lost response retry | Đã giữ draft, chặn double submit, label forms | Browser RT-01/13 + pending buttons/history/401 | browser.json; screenshots | đạt |
| W4-07 P1 | Native stack tái chạy được | Start/stop/restart thật, DB test riêng | Runbook và demo có lệnh thật | Startup + health + browser | WINDOWS_NATIVE_RUNBOOK.md | đạt |
| W4-08 P2 | LLM evidence, giới hạn nghiên cứu | Inventory export và pair hash khớp | Đã giữ base, ghi review ZIP thiếu | Manifest/output đã loại secret | evidence/llm-sft/evaluation-01 | đạt tài liệu; human review chưa có |
| W4-09 P2 | Full checks, Git, CI | Local checks đạt | Stage rõ, push FF, CI đúng SHA | Output lệnh + GitHub Actions | mục Git/CI bên dưới | đang chốt CI |
| W4-10 P2 | Native Office/ứng dụng khác | Skeleton, chưa có bằng chứng Office thật | Ghi ngoài acceptance Web hiện hành | README Add-in/code | powerpoint-addin/ | ngoài phạm vi native integration |

Holdout v3 không chạy; không retrain router/LLM, sửa gold/test hoặc attestation.
Candidate chưa được promote. Điểm AI provisional không phải independent human review.

## Lỗi thực sự đã sửa và tầng sở hữu

| Lỗi/root cause | Sửa | Kiểm chứng |
|---|---|---|
| Checkpoint env tương đối phụ thuộc cwd | FastAPI/startup resolve theo project root | Unit đổi cwd; native loaded path/hash |
| Startup nhận “status=ok” của service khác là DUSN-X, fixed port; có hướng dẫn kill theo tên | Identity cụ thể, preflight cả hai cổng, config/source/binary hashes, cổng cấu hình, stop verified PID | RT-16 foreign server còn sống; start/stop/restart thật |
| Windows venv launcher khác listening child PID | Stop helper xác minh live parent thuộc repo và PID creation time | Stop/restart helper thực chạy |
| Provider bắt mọi exception rồi fallback, che HTTP/schema/JSON/timeout; health OpenAI chỉ nhìn key | Một native attempt, validate done/content/model/tokens, lỗi mã hóa an toàn; model existence health | RT-10/11; JSON/schema/HTTP regression; external OpenAI chưa runtime |
| Gateway timeout bằng provider timeout, thiếu nhánh timeout; exception message ra client | Timeout cấu hình90s,503/504 rõ và không raw exception | .NET build; native error forwarding; chưa timing thử504 có kiểm soát |
| PUT vẫn sửa inactive original và không rollback cả supersede | Active guard và transaction context | Native PUT retry404/1 active; regression DB trigger rollback |
| REST pending không cùng lock kết nối SQLite với chat | Wrapper RLock quanh transaction | Full suite atomic/concurrent tests; native pending confirm/reject |
| Retry lưu mới hoặc mất success response có thể lặp mutation | Durable per-user request receipt/reservation; replay message ID/version, không thêm state/event/memory | RT-02/08; browser drop response sau ghi thật; thêm lượt thành công rồi retry thẻ cũ |
| Replay response có thể mang provider_called của lần sinh cũ | Replay source/calledfalse/null provider; original_provenance riêng | Native llm_replay + regression unit |
| State malformed bị bỏ qua âm thầm; GET gán schema/model hiện tại cho blob cũ | Reject malformed409; metadata stored/compatible/reset reason rõ | Isolated native state invalid; schema/model tests |
| Token TTL seconds bị làm tròn tối thiểu1h | Giữ chính xác seconds | Native TTL1s rồi401 |
| Web mất draft/lỗi chỉ console, expired auth không chuyển login, mutation double-click | Giữ text/request ID theo từng lỗi, disable khi pending,401 clear token, label modal | Chromium browser.json, Node safe render |

## File thay đổi và lý do

- `python/apps/ai_api/{main,memory,provider,auth,llm_evaluation}.py`: correctness,
  checkpoint/config identity, transaction/retry/state/TTL/provenance/provider contract.
- `gateway-dotnet/Program.cs`: binary identity, proxy timeout và lỗi không lộ internals.
- `start-local.ps1`, `scripts/LocalHealth.psm1`, `scripts/stop-local.ps1`, `.env.example`:
  native vận hành lại được, giữ default SQLite cũ `python/data`, không đụng DB cá nhân.
- `web-ui/app.js`: giữ framework/style, hoàn thiện lỗi/retry/401/loading/labels.
- `python/tests/test_week4_integration.py`: regression cho các root cause trên;
  ba fixture transport tests cũ thêm `done=true` đúng schema; không sửa gold/data.
- `scripts/verify_week4_runtime.py`, `scripts/verify_week4_web.py`: tái chạy acceptance
  qua mạng/browser thật, cấu hình lỗi trong process/DB mới, không benchmark holdout.
- README/ARCHITECTURE/CHAT_RESPONSE_CONTRACT/WEEK3 docs: phân biệt hiện hành/lịch sử.
- Runbook/demo/báo cáo và `docs/evidence/week4`, `docs/evidence/llm-sft/evaluation-01`:
  artifact công khai đã lọc, không copy auth headers/password/token/DB/weights/ZIP.

## Runtime thực chạy

Windows native, FastAPI8000/Gateway+Web8080/Ollama11434, router CPU, Ollama0.35.0.
Checkpoint SHA `56f56e6d61afc264fb02d690d2872fb3ac5db9749a659c8493fd9d99eab7e7b1`;
model version `checkpoint:router.pt:sha256-56f56e6d61af:config-03b14389ce98`.
Base vẫn `qwen2.5:0.5b`; candidate tag`:latest` có trong tags. DB scratch
`runtime/week4-native-ai`, Gateway scratch `runtime/week4-native-gateway`.
Không dùng tài khoản người thật. PowerPoint event trong HTTP script cũ là mô phỏng,
không coi là native Office bằng chứng.

RT-01/13 và UX: Chromium thật, screenshots pending/network retry/XSS/mobile.
RT-02–09/12/14: HTTP thật qua Gateway, read-only SQLite đối soát chính user test.
RT-10: cấu hình URL Ollama vào port trống trong stack riêng, không tắt Ollama chính.
RT-11: model tên không tồn tại trên Ollama thật, stack/DB riêng.
RT-15: file thiếu và file sai riêng, không sửa checkpoint gốc.
RT-16: Python HTTP server không phải DUSN-X chiếm cổng yêu cầu; startup từ chối trước
launch, server vẫn chạy. Test tự stop đúng child handle của mình sau đó.
State malformed được chèn chỉ trong DB scratch mới; API409, version5 giữ nguyên,
không thêm event. Token expiry dùng process cấu hìnhTTL1s riêng, không sửa token thật.
Tất cả process lỗi do script tạo đã được thu hồi; main stack health vẫn đúng.

Các lượt đầu được giữ local, không overwrite để che lỗi: runtime-01 cuối fail vì
assertion dự kiến foreign JSON health nhưng Python server trả404, được sửa criterion
identity-unverified (vẫn yêu cầu nonzero, server sống và không launch DUSN-X).
Browser mobile đầu chụp giữa animation sidebar; lượt sau chờ geometry settled,
không dùng screenshot bị che để claim UX. Không thay assertion chất lượng benchmark.

## Lệnh và kết quả

| Kiểm tra | Lệnh | Kết quả đo |
|---|---|---|
| Python full | `python/.venv/Scripts/python.exe -m pytest python/tests -q --tb=short` | 193 passed (lượt cuối xem evidence/checks.json) |
| Web Node | `node --test web-ui/app.test.js` | 11 passed |
| .NET Release build | `dotnet build gateway-dotnet/Dusnx.Gateway.csproj -c Release` | 0 warnings/errors |
| Gateway tests | `dotnet run --project gateway-dotnet.tests/Dusnx.Gateway.Tests.csproj -c Release` | 7/7 passed |
| PowerShell health | `./scripts/tests/local-health.tests.ps1` | 6/6 passed |
| Syntax | `python -m compileall -q python/apps python/src python/scripts scripts` | passed |
| Whitespace | `git diff --check`, sau stage `git diff --cached --check` | passed; JSON runtime normalize LF qua gitattributes |
| Native | `scripts/verify_week4_runtime.py --data-dir runtime/week4-native-ai --output-dir runtime/week4-runtime-delivery` | runtime.json |
| Browser | `scripts/verify_week4_web.py --output-dir runtime/week4-browser-delivery` | browser.json |

Sandbox Windows chặn Node spawn EPERM và pytest tmp ACL; rerun được cấp quyền ngoài
sandbox, không bỏ tests. Build lần đầu phát hiện edit catch sai biến, đã sửa và
build lại đạt. Fixture Ollama cũ thiếu done gây2 failures; update fixture completed
response và thêm tests malformed/partial, không nới schema để tests xanh.
CI có tiny offline pipeline fixtures theo workflow cũ; chúng không train lại
router Colab/LoRA sản phẩm và không chạy Holdoutv3.

## Giới hạn, phần chưa nghiệm thu và ngoài phạm vi

Không có P0 correctness đã biết bị bỏ qua trong acceptance đã chạy. Chưa tìm thấy
file kiến trúc người dùng nêu hoặc kế hoạch Tuần4 độc lập; bảng dựa yêu cầu task
và contract hiện có. Office/Zalo/Redis/SQLServer/MinIO/RAG là skeleton/hướng mở rộng,
không nghiệm thu native và không xây thành dự án mới. UI feedback chưa có flow,
API feedback/state contract có tests nhưng không thêm UI feedback ngoài thiết kế.

Retrieval còn heuristic/top15, không đảm bảo mọi paraphrase. Chưa nghiệm thu tải cao,
deployment public, external OpenAI hoặc mọi fault HTTP504/schema qua endpoint thật.
Auth SHA256+salt và legacy dev routes là giới hạn local prototype; không tuyên bố
production security. Native một FastAPI worker; receipt dở dang trả409 để đối soát,
không tự phục hồi mutation dở dang và không claim exactly-once phân tán.
Backup/restore đã viết bằng SQLite backup API; không thực hiện trên DB cá nhân.
Research promotion/human content review còn mở, không chặn nghiệm thu tích hợp Web
với base; không gọi Tuần3 research gate/promotion đã hoàn tất.

LLM review ZIP thiếu; AI4/8 vs3/8 chỉ là thông tin người dùng nêu, không independent
human review. Candidate human-test-003 regression được giữ trong raw outputs.
Không đổi dataset/test/attestation, không train lại sản phẩm, Holdoutv3 chưa chạy.
Runbook: [WINDOWS_NATIVE_RUNBOOK](WINDOWS_NATIVE_RUNBOOK.md).
Demo/bảy bước ML: [WEEK4_DEMO_AND_ML_REPORT](WEEK4_DEMO_AND_ML_REPORT.md).

## Git/CI

Remote `git@github.com:quocdoanhdang2-sketch/dusnx-platform.git`, branch main.
Fetch ban đầu: local/origin0/0. Workflow push main có4 jobs, dùng commit SHA cụ thể.
Commit/push fast-forward và CI sẽ được ghi ở checkpoint bàn giao sau kiểm staged.
Thay đổi có sẵn import script không stage. Không checkpoint/GGUF/ZIP/DB/runtime
cá nhân/.env/token/credentials trong commit.
