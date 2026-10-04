# DUSN-X public deployment guide

Public entry duy nhất là reverse proxy/Gateway qua HTTPS. Không expose FastAPI hoặc Ollama.
Copy biến từ `.env.example` vào secret store của môi trường; không commit `.env`. Đặt
`ASPNETCORE_ALLOWEDHOSTS`, `DUSNX_CORS_ORIGINS`, rate/body limits và hostname thật. Inspector,
LLM evaluation và debug giữ `0`. Terminate TLS tại reverse proxy, chuyển Host/X-Forwarded-For,
đặt timeout proxy lớn hơn provider timeout, giới hạn body 1 MiB và backup SQLite bằng API backup
khi service được quiesce theo runbook Windows.

Gateway đặt security headers, CORS allowlist, fixed-window rate limit và body limit. Production
cần secret manager, log aggregation có redaction, certificate rotation, persistent volume,
readiness theo service identity/checkpoint/provider/model. Cấu hình repo chỉ là template; chưa có
domain, TLS certificate, HA hoặc bằng chứng production capacity.
