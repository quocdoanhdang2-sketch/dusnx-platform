# Performance and security report

Phạm vi chỉ local/authorized. Không đánh dịch vụ ngoài dự án. Tuần 4 đã kiểm auth invalid/expired,
isolation, retry, XSS và provider faults. Giai đoạn này thêm CORS allowlist, host allowlist template,
security headers, request body 1 MiB và rate limit 120 request/phút/IP. Các phép đo p50/p95,
throughput, oversized/invalid content-type/rate-limit runtime sẽ được ghi sau khi chạy stack mới;
không suy ra năng lực production từ laptop.

Dependency audit chỉ được kết luận khi công cụ thật chạy. ZIP/import dùng verifier chống absolute,
`..`, symlink và checksum; không đưa token, DB, raw log hay model vào evidence.

CSP hiện cần `script-src 'unsafe-inline'` vì Web cũ dùng inline event attributes. Nội dung
user/model vẫn chỉ render bằng `textContent`, nhưng bỏ inline handlers là việc hardening còn lại
trước public production; không tuyên bố CSP hiện tại đạt mức strict.
