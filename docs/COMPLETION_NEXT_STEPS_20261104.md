# DUSN-X: phần hoàn thiện tiếp theo, không thay kiến trúc

Đối chiếu main `48c0ec82949b27779de04bbdce80027b90d8c3f3` và quality
`465ddd4f7a2f2a95d86163109d3ab768bc82d71c`. Đây là tài liệu bổ sung; không thay báo
cáo lịch sử. Không gọi hệ thống production-ready hoặc candidate đã đạt chất lượng.

## Phần sửa độc lập

- Chuyển 28 event handler trong HTML thành action name với dispatch allowlist trong
  `app.js`; không eval chuỗi attribute. Giữ chức năng đăng nhập, chat, history,
  memory, project, timeline và modal.
- Gateway bỏ `unsafe-inline` khỏi script-src, thêm script-src-attr 'none'.
  style-src vẫn cho inline style; connect-src vẫn như trước. Không tuyên bố toàn bộ
  CSP là strict hoặc mọi nguy cơ XSS đã được xử lý.
- `scripts/verify_local_readiness.py` dùng Stack/API hiện có, DB mới, HTTP và
  Chromium thật; đo read workloads và enforcement CSP/rate limit. Không gọi LLM,
  không thay kiểm thử generation, không đo năng lực production.
- `scripts/plan_retention.py`: chỉ thống kê read-only theo yêu cầu chat/event 90
  ngày, backup 30 ngày. Không có apply/purge/delete. Phải review trước khi áp dụng.
  Event dùng thời gian ghi server, không dùng timestamp do client khai.
- Audit PyPI trên virtualenv phát hiện advisory trong pip/setuptools. Đã cập nhật
  công cụ local lên pip 26.3, setuptools 84.2.1 và nâng build requirement lên
  setuptools>=84.1. Wheel build đã chạy thành công. Audit lại có 50 mục, không có
  advisory ở các mục được audit; package nội bộ và torch 2.8.0+cpu bị skip, không
  phải bằng chứng chúng đã được audit. Audit NuGet không báo package dễ tổn thương;
  không bao gồm kiểm chứng CVE của .NET shared runtime hoặc OS/container.

## Review dữ liệu v2 đúng hash hiện tại

Gói mới: [124 mục train/validation](evidence/completion-readiness-20261104/v2-human-review/review.md),
[CSV để người thật điền](evidence/completion-readiness-20261104/v2-human-review/review.csv),
[manifest hash nguồn](evidence/completion-readiness-20261104/v2-human-review/review_manifest.json).
Xuất bằng script hiện có từ datasets/llm_sft_v2, không sửa dữ liệu hoặc tự duyệt.
Mọi decision/reviewer/reviewed_at còn trống. Không có receipt mới.

1. Người duyệt đọc đủ 124 mục, điền approve/revise, tên thật hoặc định danh reviewer,
   reviewed_at có timezone; giải thích mọi revision. Không sửa cột nguồn.
2. Một người viết 6–12 test v2 độc lập theo schema repo, trước khi xem prediction;
   người thứ hai review. Không lấy test AI viết làm bằng chứng human-authored.
3. Đối chiếu hash nguồn, receipt, attestation bằng công cụ hiện có trước khi lock.
   Không dùng receipt v1 hoặc gói cũ chỉ vì cùng số dòng.
4. Chỉ train/evaluate chính thức sau gate đạt; giữ holdout v3 đóng.

## Runtime và chính sách retention

```bash
# Từ root repo; cần .NET 8 trên PATH và virtualenv đã cài dependency.
python scripts/verify_local_readiness.py --output-dir runtime/readiness-NEW --chromium /usr/bin/chromium
python scripts/verify_memory_reliability.py --output-dir runtime/memory-NEW
python scripts/verify_sqlite_backup_restore.py --output-dir runtime/restore-NEW
python scripts/plan_retention.py --data-dir runtime/TEST/ai --backup-dir runtime/TEST/backups --output runtime/retention-NEW.json
```

Trên Windows dùng executable Python/Chromium thực theo runbook. Không chạy trên DB
cá nhân chỉ để tạo evidence. Output readiness phải mới; không dùng report cũ.
Backup harness level 2 skipped không phải kiểm chứng backup cá nhân.

Retention chưa phải account purge: chat_receipts có bản sao response nhưng không
có timestamp; memory version, pending decision, session title, hidden state, JSON
Gateway, log và backup generation còn cần chính sách riêng. File mtime chỉ ước lượng
tuổi backup, không đủ cho quyết định xóa. Không sửa schema/cron/purge khi chưa review
báo cáo và xử lý các phụ thuộc đó.

## Prompt tiếp tục cho Codex trên Windows

```text
Tiếp tục DUSN-X bằng code và runtime thật, giữ kiến trúc Gateway/FastAPI/router/
SQLite/provider. Fetch và đọc SHA thực; giữ stash và dữ liệu cá nhân. Không reset,
force push, mở holdout hoặc sửa output lịch sử.

1. Review diff nhánh hardening, kiểm tra tương thích với main mới và quality PR #7.
   Chạy Chromium thật để kiểm tra external actions, CSP, auth/chat/history/modal.
   Không suy năng lực generation từ health hoặc provider_error xử lý đúng.
2. Chẩn đoán pipeline trên Windows: xác minh service identity/source/binary ở
   Gateway /health, /v1/health, FastAPI /health và Ollama /api/version, /api/tags.
   Nếu /v1/health không tới FastAPI, xem log/startup/AI_API_URL/port owner và sửa
   nguyên nhân; không kill process theo cổng hoặc coi HTTP 200 của app khác là đạt.
3. Sửa topic-shift và literal trên quality branch bằng trace history/prompt/raw
   content/sanitizer/guard/persistence. Đọc CASE_06 factual; ngôn ngữ đúng không
   chứng minh kiến thức đúng. Không hardcode đáp án hoặc hạ rubric để pass.
4. Gói 124 mục human review đã xuất trong docs/evidence/completion-readiness-20261104.
   Có thể đưa gợi ý review riêng, không điền chữ ký/receipt thay người. Chưa có
   human-authored test và independent reviewer thì không lock/train/promote.
5. Nghiệm thu Office Desktop trên SHA xác định: proposal, đổi slide, đổi shape,
   sửa text, Apply target đúng và trường hợp lỗi. Không dùng mock thay Desktop.
6. Chính sách người dùng: chat/event 90 ngày, backup 30 ngày, xem lại trước apply.
   Chạy plan_retention dry-run; không delete/purge. Xử lý thiết kế receipt không có
   timestamp và dữ liệu sao chép/backup trước khi đề xuất implementation xóa.
7. Đo tải đọc và generation riêng; báo workload, concurrency, duration, p50/p95,
   error/429. Làm dependency audit và TLS/ingress/log review trên môi trường thật.
8. Sửa độc lập đủ bằng chứng: commit/push, tạo PR và xác minh CI đúng SHA; merge
   theo quy trình thường. Quality chưa đạt giữ riêng, không đổi default model.

Bàn giao bằng SHA remote, commands/exits, evidence mới, failure còn lại và giới hạn.
Không tuyên bố production-ready, human-reviewed hay hoàn thành khi thiếu bằng chứng.
```

Word/Teams/image-edit/Zalo OA và RAG retriever vẫn cần adapter, quyền/provider và
acceptance riêng nếu nằm trong phạm vi bàn giao. Không xóa chúng khỏi phạm vi để
đánh dấu hoàn tất. Không tự gửi tin ra ngoài hoặc triển khai production.
