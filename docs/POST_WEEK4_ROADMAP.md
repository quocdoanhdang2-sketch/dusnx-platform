# DUSN-X — acceptance sau Tuần 4

Mốc đầu vào: `7a15ee13217f2239d4bf9780bded6a8163831505`. Web là sản phẩm chính;
PowerPoint là tích hợp minh chứng. Router, SQLite memory và text LLM là ba thành phần khác nhau.

| ID | Ưu tiên | Yêu cầu | Trạng thái ban đầu | Cách triển khai | Cách kiểm chứng | Bằng chứng | Kết quả |
|---|---|---|---|---|---|---|---|
| DEMO-01 | P0 | Demo Web 18 luồng | Tuần 4 đã đạt | Giữ retry/auth/memory; thêm script lặp lại | HTTP + Chromium | `evidence/post-week4` | chờ runtime lại |
| OBS-01 | P0 | Inspector an toàn | Chưa có | Metadata chat lọc, env opt-in, UI details/copy | auth/isolation/off/provenance tests | tests + screenshot | code hoàn tất |
| I18N-01 | P0 | VI/EN/auto | Chỉ VI | detector rule, preference memory, provider policy, UI selector | I18N-01–12 | tests/runtime | code nền hoàn tất; cần mở rộng bản dịch UI |
| LLMV2-01 | P1 | Data v2 tách v1 | Chưa có | AI draft 100/24/16, provenance/checksum | validator/audit | `evidence/llm-sft-v2` | draft; chưa qua review |
| LLMV2-02 | P1 | Candidate v2 | Chưa có | Notebook/config chỉ sau data gate | CPU smoke/Colab artifact | completion report | bị chặn bởi review/chất lượng data |
| HOLDOUT-01 | P0 | Giữ protocol v3 | Chưa independent review | Chỉ hash/manifest/gate; không inference | manifest/receipt | completion report | không mở |
| PPT-01 | P1 | Native Office task pane | Skeleton | Auth/session/chat, selected-slide context, proposal/apply | Node mock, manifest, HTTPS pane, Desktop sideload | runbook/demo | code/mock; Desktop cần người dùng |
| DEPLOY-01 | P1 | Public config tái tạo | Local defaults | CORS allowlist, host, headers, size/rate/timeouts, reverse proxy | local security probes | deployment guide/report | cấu hình hoàn tất; chưa public |
| PERF-01 | P2 | Load local giới hạn | Chưa có | health/history/chat scratch, không spam mutation | p50/p95/error/throughput | performance report | chờ runtime |
| SEC-01 | P0 | Auth/IDOR/XSS/CORS/payload/rate | Một phần Tuần 4 | regression + local probes + secret scan | suite/security script | performance report | đang kiểm chứng |
| DOC-01 | P1 | Runbook/demo song ngữ | Chưa có | Tài liệu mới, giới hạn đúng | review links/commands | docs | đang hoàn thiện |
| CI-01 | P0 | Commit/push/Actions đúng SHA | CI Tuần 4 xanh | stage rõ, không stage user file/artifact | local full suite + Actions | completion report | chờ cuối |

Không mở rộng Word hoặc Zalo. Candidate v1 không được promote. Evaluation endpoint và Inspector
tắt mặc định. `holdout_v3` không được đưa vào model/rule/baseline/scorer khi gate chưa đủ.
