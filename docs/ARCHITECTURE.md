# DUSN-X Architecture v0.2 — Phase 1

## Hiện hành Tuần 4

Đường Web cá nhân hóa dùng Gateway ASP.NET Core HttpClient proxy → FastAPI.
Opaque Bearer token lấy user từ SQLite auth, memory/session/pending/state/events
trong SQLite; không dùng linkedUserId của client cho đường `/v1/me/*`.
Router checkpoint PyTorch cập nhật vector recurrent và dự đoán routing; rules
nghiệp vụ quyết định CRUD/xác nhận/clarification. Recall trích memory bằng template
không gọi provider. Generation riêng gọi Ollama base `qwen2.5:0.5b`.
Candidate LoRA chỉ evaluation, không thay router hoặc model base mặc định.

Native startup root-resolves checkpoint/config, xác minh service/source/binary,
không kill port owner, cho cấu hình cổng. Request ID/receipt bền trong SQLite bảo vệ
retry chat từ Web. Transaction supersede và khóa kết nối được dùng chung cho chat/REST.
Health/source provenance, DB memory và hidden state vector là các khái niệm riêng.

Diagram/Phase2 adapters bên dưới là kiến trúc Phase1 lịch sử và hướng mở rộng,
không có nghĩa SQL Server/Redis/MinIO/JWT/RAG/native Office đã triển khai.
Xem [acceptance Tuần4](WEEK4_COMPLETION_REPORT.md) và [runbook](WINDOWS_NATIVE_RUNBOOK.md).

```text
Web / PowerPoint / Zalo
        |
        v
ASP.NET Core Gateway
        |
        +-- Identity Mapping: platform_user_id -> global_user_id
        +-- State continuity + JSON persistence
        +-- Presentation Job Queue
        +-- Zalo Webhook Queue
        +-- SignalR Job Hub
        |
        v
FastAPI AI Service
        |
        v
DUSN-X Core
  +-- Event Encoder
  +-- Global State
  +-- Platform State
  +-- Task State
  +-- Time-aware decay/gating
        |
        v
Adaptive Agent Router
  +-- Conversation Agent
  +-- Search/RAG Agent
  +-- Productivity Agent
        |
        v
Structured output + next state
```

## MVP vs Pilot

Phase 1 lưu state xuống `runtime/gateway-data` và sử dụng `Channel<T>` trong tiến trình cho job queue. Cách này giúp chạy nhẹ, không cần bật toàn bộ hạ tầng ngay ngày đầu.

Phase 2 sẽ thay thế từng adapter nhưng giữ nguyên API contract:

- JSON state store → SQL Server + Redis.
- In-process Channel → Redis Streams.
- Outline result → MinIO artifact.
- Bootstrap rules → trained DUSN-X checkpoint.
- Development identity → JWT + linked identity table.

## Local event timeline

Gateway appends one compact JSON object per processed event to
`runtime/gateway-data/events.jsonl`. Writes are serialized so concurrent requests cannot
interleave bytes. Processing is also serialized per resolved `global_user_id`, preserving
state/event order for one linked identity while allowing unrelated users to proceed.

`GET /api/v1/history/{platform}/{platformUserId}` resolves the same identity as event
ingestion, projects only timeline fields, skips blank or locally damaged legacy lines, and
returns at most 100 records. Results are newest-first; pass `next_cursor` back as `before`
to read the next older page. The physical JSONL line position is the stable tie-breaker,
including when timestamps are equal.

This endpoint is a development/local observability feature. It accepts loopback requests
and local browser origins by default and has no production authentication. `DUSNX_ALLOW_REMOTE_DEV_HISTORY=true`
is an explicit development override, not an authentication mechanism.
