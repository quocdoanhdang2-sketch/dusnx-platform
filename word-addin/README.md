# DUSN-X Word Add-in

Office.js task pane cho Microsoft Word. Người dùng đăng nhập DUSN-X, chọn session, chọn một
đoạn văn trong tài liệu, tạo proposal từ LLM và chỉ ghi vào tài liệu khi bấm **Apply**.

- `manifest.xml` — TaskPaneApp, `WordApi 1.1`, `ReadWriteDocument`, trỏ tới
  `https://localhost:3001/word-taskpane.html`.
- `word-taskpane.html` — UI đăng nhập/session/instruction/proposal/provenance.
- `word-taskpane.js` — toàn bộ logic; token opaque chỉ nằm trong RAM.
- `dev-server.js` — HTTPS server dev dùng chung cho Word và PowerPoint: chỉ phục vụ allowlist
  asset (Word task pane, PowerPoint task pane, `deck-template.pptx`), proxy `/v1/*` same-origin
  tới Gateway loopback, CSP + `no-store` + giới hạn body 64 KiB.
- `word-taskpane.test.js` — 15 unit test với Word host giả.
- `dev-server.test.js` — 9 test cho allowlist asset, kiểm tra Gateway URL, đích proxy, lọc
  header, CSP và asset thiếu.

## Hành vi an toàn

- Chỉ gửi **đoạn đang chọn** và instruction; không gửi toàn tài liệu.
- Selection rỗng, quá 4000 ký tự hoặc không phải văn bản bị từ chối trước khi gọi provider.
- Proposal chỉ được tạo khi response có provenance thực:
  `provider_ok === true`, `response_source === "llm"`, `provider_called === true`,
  `provider_used`/`model_used` không rỗng.
- Từ chối proposal rỗng, chứa ký tự điều khiển, bắt đầu bằng JSON/code fence, hoặc không
  làm thay đổi text gốc.
- Apply đọc lại selection và từ chối nếu text/start/end, session hoặc trạng thái đăng nhập
  đã đổi; proposal bị xóa sau mọi lần Apply (kể cả khi từ chối).
- Chọn được chế độ Apply: **Replace selected text** hoặc **Insert new paragraph after
  selection**. Chế độ được chốt lúc tạo proposal; đổi chế độ sẽ xóa proposal cũ.
- Giữ paragraph break cuối của selection khi Replace để không nối đoạn với đoạn kế tiếp.
- Logout xóa token + proposal ngay, hủy request đang bay bằng `AbortController` và làm mất
  hiệu lực response đến muộn.
- Request mặc định same-origin (`/v1/...`); chỉ đặt `DUSNX_GATEWAY` khi chạy sau reverse proxy
  khác origin, và không cần inject script vào HTML khi dùng `dev-server.js`.

## Chạy thử

Xem [docs/WORD_ADDIN_RUNBOOK.md](../docs/WORD_ADDIN_RUNBOOK.md). Bằng chứng Word Desktop
thật: [docs/evidence/word-addin-desktop-20261106](../docs/evidence/word-addin-desktop-20261106/README.md).

## Test

```bash
node --test word-addin/word-taskpane.test.js word-addin/dev-server.test.js
```

Kết quả hiện tại: 26/26 pass (17 task pane + 9 dev server; tổng Node suite 66/66).
