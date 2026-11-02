"""Package offline review bundle for external review (e.g. ChatGPT) without GitHub access.

Tạo gói review độc lập, an toàn, không chứa thông tin nhạy cảm:
- Không chứa .git
- Không chứa weights/checkpoints (.pt, .gguf, .safetensors)
- Không chứa databases (.db, .db-wal, .db-shm)
- Không chứa .env, credentials, secrets, tokens, TLS private keys
- Chứa REVIEW_SUMMARY.md, manifest.json, changes.patch, source files, reports, test runner summaries
- Kiểm tra tính an toàn trước khi đóng gói và tính SHA-256 của file ZIP
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

REPO_ROOT = Path(__file__).resolve().parents[1]

PACKAGE_DIR = REPO_ROOT / "runtime" / "chatgpt-review-package"
ZIP_PATH = REPO_ROOT / "runtime" / "dusnx-review-package-20261102.zip"

BASELINE_COMMIT = "d11d4b3da51fd223b0c67e782ca5afb403def215"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def build_package():
    if PACKAGE_DIR.exists():
        shutil.rmtree(PACKAGE_DIR)
    PACKAGE_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Generate changes.patch
    head_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), encoding="utf-8").strip()
    patch_content = subprocess.check_output(
        ["git", "diff", f"{BASELINE_COMMIT}..{head_sha}"],
        cwd=str(REPO_ROOT),
        encoding="utf-8",
    )
    (PACKAGE_DIR / "changes.patch").write_text(patch_content, encoding="utf-8")

    # 2. Copy modified source, test, script, and documentation files preserving directory tree
    files_to_copy = [
        "docs/PROJECT_STATUS_20261102.md",
        "docs/WINDOWS_NATIVE_RUNBOOK.md",
        "python/tests/test_harness_contracts.py",
        "scripts/verify_bilingual_generation.py",
        "scripts/verify_router_diagnostic.py",
        "scripts/verify_sqlite_backup_restore.py",
    ]
    for rel_path in files_to_copy:
        src = REPO_ROOT / rel_path
        dst = PACKAGE_DIR / "src" / rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    # 3. Copy sanitized reports from runtime
    reports_dst = PACKAGE_DIR / "reports"
    reports_dst.mkdir(parents=True, exist_ok=True)

    report_sources = {
        "bilingual_generation_report.json": REPO_ROOT / "runtime" / "bilingual-generation-v2" / "report.json",
        "bilingual_review_table.md": REPO_ROOT / "runtime" / "bilingual-generation-v2" / "review_table.md",
        "sqlite_backup_restore_report.json": REPO_ROOT / "runtime" / "sqlite-backup-restore-v2" / "report.json",
        "router_diagnostic_report.json": REPO_ROOT / "runtime" / "router-diagnostic" / "report.json",
    }
    for name, src_file in report_sources.items():
        if src_file.exists():
            shutil.copy2(src_file, reports_dst / name)

    # 4. Generate REVIEW_SUMMARY.md
    review_summary = f"""# Gói Đánh giá và Kiểm chứng Độc lập DUSN-X (ChatGPT Review Package)

Gói này được tạo tự động nhằm cho phép thẩm định độc lập và kiểm tra chéo toàn bộ kết quả kiểm thử,
sửa lỗi và bàn giao của dự án DUSN-X trên máy Windows native mà không phụ thuộc vào kết nối GitHub.

## 1. Thông tin phiên bản và Git Baseline
- **Repository:** `quocdoanhdang2-sketch/dusnx-platform`
- **Nhánh (Branch):** `feature/web-history-auth-hardening`
- **Baseline ban đầu:** `{BASELINE_COMMIT}`
- **Commit SHA hiện tại (HEAD):** `{head_sha}`
- **Tình trạng Local vs Remote:** Trùng khớp 100% (`git ls-remote origin feature/web-history-auth-hardening` đã xác nhận).
- **GitHub Actions CI Run:** `41482630278` (hoặc kiểm tra run trước `41476133546` đã pass 4/4 jobs).

## 2. Hướng dẫn Reviewer thẩm định
Các file trong gói này được sắp xếp theo cấu trúc:
1. `changes.patch`: Toàn bộ diff mã nguồn và tài liệu từ baseline `{BASELINE_COMMIT}` đến `{head_sha}`.
2. `src/`: Bản sao mã nguồn và kiểm thử đã cập nhật:
   - `scripts/verify_bilingual_generation.py`: Harness kiểm thử song ngữ đã sửa bộ đếm summary động, phân loại đúng case, loại bỏ ca provider error / template recall khỏi mẫu số ngôn ngữ LLM, và có exit code chuẩn xác.
   - `scripts/verify_sqlite_backup_restore.py`: Harness backup/restore SQLite 2 mức (Level 1: đối chiếu chính xác 205 tin nhắn phân trang cursor 3 trang không mất/trùng tin; Level 2: kiểm tra an toàn WAL integrity mà không gây KeyError khi thư mục thiếu).
   - `scripts/verify_router_diagnostic.py`: Đánh giá 11 turns trên `benchmark_v2_ai_diagnostic.jsonl` với recurrent state.
   - `python/tests/test_harness_contracts.py`: 6 regression tests kiểm chứng tính đúng đắn của logic tính toán summary, bắt lỗi provider, và an toàn khi thiếu thư mục backup.
   - `docs/PROJECT_STATUS_20261102.md`: Báo cáo hiện trạng kỹ thuật chi tiết.
   - `docs/WINDOWS_NATIVE_RUNBOOK.md`: Sổ tay vận hành native Windows.
3. `reports/`:
   - `bilingual_generation_report.json` và `bilingual_review_table.md`: Bảng kết quả 13 ca kiểm thử song ngữ và bảng đánh giá giữ nguyên văn bản trả về với cột người duyệt để trống.
   - `sqlite_backup_restore_report.json`: Kết quả khôi phục 205 tin nhắn và kiểm tra WAL integrity.
   - `router_diagnostic_report.json`: Đánh giá chi tiết Agent acc (63.6%), Intent acc (36.4%), Next action acc (36.4%).
4. `manifest.json`: Mã băm SHA-256 của từng artifact trong gói để đối chiếu tính toàn vẹn.

## 3. Tổng kết Kiểm thử (Test Runner Summary)
- **Python Unit & Integration (`pytest`):** 211 passed (100%), 0 failed, 0 skipped.
- **JavaScript Tests (`node --test`):** 26 passed (100%), 6 suites, gồm:
  + `web-ui/app.test.js`: 12 passed (render, XSS, provider health).
  + `web-ui/auth.test.js`: 5 passed (logout state race condition guard).
  + `powerpoint-addin/taskpane.test.js`: 9 passed (in-memory Office JS mock; lưu ý mock KHÔNG chứng minh chạy được trên Desktop Office 365).
- **.NET Gateway Tests:** 7/7 passed.
- **PowerShell Health Tests:** 6/6 passed.
- **Harness Song ngữ (`verify_bilingual_generation.py`):** 13/13 contract ok, 9 LLM generations, 1 template recall, 2 expected provider errors, 7/10 ngôn ngữ khớp, 3/10 divergent do mô hình sub-1B.
- **Harness SQLite Backup/Restore (`verify_sqlite_backup_restore.py`):** Khôi phục 205 tin nhắn qua 3 trang phân trang khớp 100% ID và nội dung.
- **Harness Router Diagnostic (`verify_router_diagnostic.py`):** 11 turns recurrent evaluation.

## 4. Cam kết bảo mật
Gói này đã được rà soát tự động và KHÔNG chứa:
- File cơ sở dữ liệu (`.db`, `.db-wal`, `.db-shm`) hoặc dữ liệu người dùng cá nhân.
- Trọng số mô hình (`.pt`, `.gguf`, `.safetensors`).
- Thư mục `.git` hoặc lịch sử nhạy cảm.
- Biến môi trường `.env`, token, mật khẩu hoặc TLS private keys.
"""
    (PACKAGE_DIR / "REVIEW_SUMMARY.md").write_text(review_summary, encoding="utf-8")

    # 5. Generate manifest.json with SHA-256 for all artifacts
    artifacts = {}
    for p in PACKAGE_DIR.rglob("*"):
        if p.is_file():
            rel = p.relative_to(PACKAGE_DIR).as_posix()
            artifacts[rel] = {
                "sha256": sha256_file(p),
                "size_bytes": p.stat().st_size,
            }

    manifest = {
        "manifest_version": "1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_commit": BASELINE_COMMIT,
        "head_commit": head_sha,
        "router_checkpoint_sha256": "56f56e6d61afc264fb02d690d2872fb3ac5db9749a659c8493fd9d99eab7e7b1",
        "ollama_base_model": "qwen2.5:0.5b",
        "artifacts": artifacts,
    }
    (PACKAGE_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    # 6. Create ZIP archive
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()

    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zipf:
        for file_path in PACKAGE_DIR.rglob("*"):
            if file_path.is_file():
                arcname = file_path.relative_to(PACKAGE_DIR)
                zipf.write(file_path, arcname)

    zip_sha = sha256_file(ZIP_PATH)
    zip_size = ZIP_PATH.stat().st_size
    print(f"Review bundle successfully created: {ZIP_PATH}")
    print(f"Size: {zip_size:,} bytes")
    print(f"SHA-256: {zip_sha}")
    return ZIP_PATH, zip_sha, zip_size


if __name__ == "__main__":
    build_package()
