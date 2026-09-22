# GitHub và mở rộng tính năng DUSN-X

## Tên repository

Khuyến nghị chính: `dusnx-platform`.

Tên này đủ rộng để sau này thêm Word, Mobile, Telegram hoặc TikTok mà không phải đổi repository.

## Quy tắc branch

```text
main                      bản ổn định
develop                   tích hợp trước khi vào main
feature/web-workspace     Web
feature/powerpoint-addin  PowerPoint
feature/zalo-connector    Zalo
feature/dusnx-training    Model và training
feature/rag               ChromaDB/RAG
```

## Kiến trúc connector

Mỗi nền tảng mới chỉ cần chuyển dữ liệu về Canonical Event:

```json
{
  "platform": "word",
  "platform_user_id": "external-user-id",
  "event_type": "document.summarize_requested",
  "content": "Nội dung hoặc yêu cầu",
  "feedback_value": 0.0,
  "linked_user_id": "global-demo-001"
}
```

Không để connector tự sửa Global User State. Chỉ FastAPI/DUSN-X được cập nhật state.

## Tính năng có thể thêm

| Nhóm | Tính năng | Giai đoạn |
|---|---|---:|
| Security | JWT, refresh token, role, rate limit | Phase 2 |
| PowerPoint | Chèn slide thật, theme, speaker notes | Phase 2 |
| Zalo | OA signature, gửi phản hồi, retry/dead-letter | Phase 2 |
| State | SQL Server + Redis State Store | Phase 2 |
| RAG | ChromaDB ingestion/retrieval | Phase 2 |
| MLOps | MLflow, dataset manifest, model registry | Phase 3 |
| Connectors | Word, Telegram, Mobile | Phase 3 |
| Research | Baseline, ablation, drift evaluation | Phase 3 |
| Multimedia | YOLO/MediaPipe/Image Agent | Phase 4 |

## Quy tắc thêm Agent

Mỗi Agent có contract chung:

```text
AgentInput:
- global_user_id
- current_state
- platform
- task
- context

AgentOutput:
- result
- confidence
- evidence
- feedback_request
```

Agent mới không gọi trực tiếp SQL Server hoặc sửa state. Agent trả kết quả về Orchestrator; DUSN-X quyết định cập nhật state.

## Không đưa lên GitHub

- `.env`
- Zalo secret/token
- SQL Server password
- Dataset người dùng thật
- Checkpoint dung lượng lớn
- File log có dữ liệu cá nhân
- Cloudflare Tunnel credential
