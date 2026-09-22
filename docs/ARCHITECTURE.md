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
