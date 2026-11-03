# Sửa cơ chế nghiệm thu và đóng gói — 03/11/2026

Baseline review: 4900599aaf2a223a9123969c79ee429f9e35807e. Đây là thay đổi code
kiểm chứng và bàn giao; không phải xác nhận sản phẩm đã hoàn thành mọi yêu cầu.

- generation_contract dùng chung cho mọi ca LLM, gồm provider/model/source/reply.
  Bổ sung provenance cho các ca ngữ cảnh, preference và hai user.
- --strict-language thất bại khi còn divergent hoặc uncertain.
- --strict-quality thất bại khi có repeated_lines. Cờ này bắt được output lặp từ
  CASE_01 lịch sử, nhưng không đo factuality hoặc thay thế review nội dung.
- Các regression chạy CLI với input mô phỏng kiểm chứng exit code thật, tách rõ
  đây là regression của harness, không phải generation qua Ollama thật.
- Package lấy source từ đúng commit Git, từ chối dirty tree, kiểm tra patch và
  allowlist text, không copy runtime. Không xóa gói cũ hoặc ghi đè ZIP.
- Manifest không hardcode test/CI/remote. Remote chỉ được đọc khi --verify-remote;
  CI luôn not_checked trong packager, test execution là not_run_by_packager.
- Credential scan chỉ bắt mẫu có độ tin cậy cao, không bảo đảm phát hiện mọi bí mật.
  Các report committed trong docs là bằng chứng lịch sử, không phải lượt chạy mới.

Regression mới: python/tests/test_handover_guards.py; regression trước đó vẫn giữ.
Prompt hoàn tất sản phẩm trên Windows: docs/PROMPT_RELEASE_COMPLETION.md.
Không thay đổi trọng số/model, không sửa historical outputs để che lỗi.
Generation/quality thực tế phải chạy lại trên Windows có Ollama/model và đạt các
check bắt buộc trước khi xác nhận bàn giao hoàn thành.

Lệnh package (sau commit; thay BASELINE bằng SHA đã xác minh):

```powershell
& python/.venv/Scripts/python.exe scripts/package_review_bundle.py --baseline BASELINE --verify-remote
```

Lệnh kiểm tra ngôn ngữ/nội dung (output-dir phải mới):

```powershell
& python/.venv/Scripts/python.exe scripts/verify_bilingual_generation.py --output-dir runtime/release-quality-new-run --strict-language --strict-quality
```

Kết quả kiểm tra local sau sửa:
- Full pytest: 230 passed, không skip, 31.23s.
- Node Web/auth/Office mock: 26 passed.
- 25 regression của hai file harness contract/handover guards đạt.
- Ruff cho packager và regression mới, py_compile và git diff --check đạt.
- Đối chiếu output CASE_01 lịch sử: repeated_lines được phát hiện; không chạy lại
  generation Windows trong lượt cloud này, không thay thế evidence cũ.
