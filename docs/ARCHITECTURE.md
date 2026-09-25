# DUSN-X Architecture v0.2 — Phase 1

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
