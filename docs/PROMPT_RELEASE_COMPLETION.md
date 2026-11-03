# Prompt hoàn tất sản phẩm và bàn giao có kiểm chứng

Dán nội dung dưới đây cho Codex/Antigravity trên Windows, trong repo DUSN-X.

---

Hãy trực tiếp hoàn tất sản phẩm theo yêu cầu hiện hành của repository. Người dùng
muốn bàn giao hoàn thành, không chấp nhận hạ mục tiêu thành demo hoặc chỉ đổi nhãn
báo cáo. Không gọi một tính năng hoàn thành khi test bắt buộc hoặc nghiệm thu còn
thất bại. Không bịa kết quả, không nới assertion, không tự điền human review.

## 1. Baseline và phạm vi hoàn thành

- Xác minh repo, local/remote SHA, branch, dirty files, stash và công cụ thực tế.
- Đọc AGENTS.md, yêu cầu hiện hành, runbook và báo cáo; lập ma trận toàn bộ yêu cầu
  bắt buộc: chức năng, tính đúng, chất lượng nội dung, an toàn dữ liệu, vận hành,
  hiệu năng cần thiết và tích hợp. Phân biệt yêu cầu đã cam kết với hướng mở rộng.
- Không tự bỏ yêu cầu bắt buộc để tuyên bố hoàn thành. Public deploy và merge main
  không mặc nhiên được cho phép chỉ từ yêu cầu hoàn tất code.
- Tích hợp bản sửa harness/package mới nhất từ feature/web-history-auth-hardening
  sau khi đối chiếu local work. Không reset/clean/force-push/pop stash tự động.
- Giữ checkpoint gốc, DB cá nhân và các sửa có sẵn. Tạo DB/account tổng hợp riêng.

## 2. Hoàn tất generation và chất lượng thực tế

- Kiểm tra Ollama/model, API/Gateway/Web bằng HTTP và Chromium thật trên Windows.
- Xác minh checkpoint và code/process đang chạy đúng phiên bản. Không chiếm cổng
  ứng dụng khác, không kill process theo tên hàng loạt.
- Chạy harness generation với cả --strict-language và --strict-quality trên output
  mới. Nếu còn failed/divergent/uncertain/quality flags thì không ghi nghiệm thu đạt.
- Xem lại output CASE_01 từng lặp “Tái tạo và phân phối dữ liệu” nhiều lần và bị
  cắt dang dở. Khớp tiếng Việt không có nghĩa nội dung đúng/hữu ích.
- Sửa nguyên nhân ứng dụng/prompt/context/config có bằng chứng. Xác minh câu trả
  lời đúng với thông tin được cung cấp, không tự bịa tính năng dự án hoặc memory.
- Kiểm tra VI/EN/auto, cross-language, preference bền và user isolation. Mọi ca
  generation phải qua cùng generation_contract, đúng provider/model/source.
- Cờ repeated_lines chỉ là heuristic, không phải đánh giá factuality đầy đủ. Thêm
  case nội dung có kỳ vọng kiểm chứng được; không tự nhận là independent review.
- Nếu model hiện tại không đạt: đo lỗi, so sánh model thay thế bằng cấu hình tường
  minh và cùng tiêu chí. Không tự thay model phục vụ người dùng hoặc promote nếu
  gate không cho phép. Việc đổi expected_model của harness phải có provenance rõ.
- Router đã train; không retrain để chữa lỗi harness. Chỉ training khi có dữ liệu,
  quyền sử dụng, gate và tiêu chí hợp lệ. Không mở protected holdout v3.

## 3. Hoàn tất correctness và vận hành

- Auth/expiry/logout/late responses; user/project/session isolation; lịch sử dài;
  memory active/supersede/confirm/reject; retry/receipt; provider fault; DB rollback.
- Backup API, integrity và restore sang thư mục mới; đối chiếu đủ 205 message IDs,
  nội dung, thứ tự qua ba trang. Retry sau restore không trùng mutation/state.
- Phân biệt synthetic functional restore với personal backup integrity-only. Nếu
  personal restore bắt buộc, chạy trên bản sao, không ghi lên dữ liệu gốc.
- Kiểm tra startup/stop/restart/recovery; source/binary identity; cấu hình triển
  khai được hỗ trợ. Các default/skeleton hoặc chức năng chưa kiểm không được tính
  hoàn thành chỉ vì có code.
- Nếu Office Desktop là yêu cầu bắt buộc, nghiệm thu Office thật theo runbook;
  mock không thay thế. Nếu không thể chạy, ghi blocker và chưa hoàn thành mục đó.
- Tối ưu dựa trên đo lường. Thay DB lock/concurrency phải có test transaction,
  isolation, retry và lỗi đồng thời; không tuyên bố tăng tốc khi chưa đo trước/sau.

## 4. Chạy kiểm thử và ghi đúng phiên bản

- Full pytest, Node Web/auth/Office mock, .NET build/tests, PowerShell health và
  các harness thực tế: auth/history/memory/provenance/runtime/browser/bilingual/
  backup/router diagnostic được phép. Đọc tham số trước chạy.
- Regression phải tái hiện lỗi trước sửa và đạt sau sửa. Kiểm tra CLI exit code
  cho contract failure, strict-language (gồm uncertain) và strict-quality.
- Output-dir mới cho từng lượt; không xóa/chỉnh bằng chứng thất bại. Nếu exception
  giữa chừng, lưu các case đã chạy và trạng thái execution_failed, không coi case
  chưa chạy là passed.
- Ghi HEAD, dirty/patch hash, tool versions, model digest, checkpoint hash,
  commands, exit codes, số passed/failed/skipped/unrun. Test trước commit không
  được mô tả thành test chạy trên commit cuối nếu chưa xác minh tương đương.
- Tách các loại test và mẫu số chất lượng. CI xanh không thay generation/browser/
  restore trên Windows. Không bỏ quality failure để đạt tổng xanh.

## 5. Đóng gói và Git bàn giao

- Chỉ commit file thuộc nhiệm vụ; không model/DB/.env/token/raw private logs.
- Script package_review_bundle.py mới từ chối dirty tree; snapshot lấy từ git
  objects. Commit source đã review trước khi tạo ZIP. Đừng vô hiệu guard đó.
- Tạo ZIP bằng --baseline SHA đã xác minh và --output đường dẫn mới. Có thể dùng
  --verify-remote sau khi push. Script không thực thi test/CI; không bịa các kết
  quả này trong package. Báo cáo lịch sử trong docs vẫn là lịch sử.
- Tính và kiểm tra manifest/hash ZIP; scan mẫu credential chỉ là lớp hỗ trợ, vẫn
  rà soát file trước khi người dùng gửi ra ngoài.
- Push nhánh riêng, xác minh full remote SHA. Đọc CI đúng SHA nếu có quyền; nếu
  không đọc được ghi unverified, không success. Không merge main/deploy tự động.

## 6. Điều kiện bàn giao hoàn thành

Cập nhật ma trận yêu cầu bằng bằng chứng thực tế. Chỉ ghi HOÀN THÀNH khi tất cả
mục bắt buộc đã đạt và không còn lỗi chất lượng/correctness bị che bởi transport
pass. Với mục blocked/unrun, tiếp tục các phần độc lập, rồi báo đúng blocker;
không đổi cách gọi thành demo để né yêu cầu.

Bàn giao: commit/remote SHA, CI đã xác minh hoặc unverified, kết quả runner thật,
artifact manifest, ZIP hash và đường dẫn, runbook cài/chạy/backup/restore/stop,
các lỗi đã sửa và danh sách yêu cầu bắt buộc còn thiếu (nếu có).

Bắt đầu ngay bằng baseline và ma trận yêu cầu, rồi trực tiếp sửa và kiểm chứng.
Không dừng ở kế hoạch hoặc hỏi lại quyền cho công việc thông thường đã được phép.
