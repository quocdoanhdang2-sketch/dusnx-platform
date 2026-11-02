"""SQLite Backup and Restore Verification Harness.

Thực hiện kiểm chứng 2 mức độc lập:
1. Mức 1 (DB tổng hợp đầy đủ):
   - Tạo user, session, message, active/superseded memory, receipt ID trên Stack đang chạy.
   - Backup bằng SQLite Backup API (src.backup(dst)) trong khi service đang hoạt động.
   - Kiểm tra PRAGMA integrity_check trên bản backup.
   - Khôi phục (restore) sang thư mục hoàn toàn mới.
   - Khởi động Stack mới trên dữ liệu khôi phục.
   - Xác minh auth, session, memory recall (loại bỏ superseded), và tính bất biến của retry (idempotency, không tạo trùng mutation).
2. Mức 2 (Dữ liệu bảo vệ / Backup cá nhân):
   - Kiểm tra tính toàn vẹn (PRAGMA integrity_check, journal_mode WAL) trên bản sao read-only.
   - Đếm số lượng bản ghi theo bảng mà KHÔNG in hoặc dump nội dung riêng tư.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import shutil
import sqlite3
import sys

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from verify_week4_runtime import Stack


def verify_synthetic_backup_restore(out_dir: Path) -> dict:
    """Level 1: End-to-end backup, restore, and stack execution using SQLite Backup API."""
    live_stack_dir = out_dir / "synthetic_live_stack"
    backup_dir = out_dir / "synthetic_backup_files"
    restore_stack_dir = out_dir / "synthetic_restored_stack"

    backup_dir.mkdir(parents=True, exist_ok=True)
    results = {
        "status": "unverified",
        "live_creation": False,
        "sqlite_backup_api_used": False,
        "backup_integrity_checked": False,
        "restored_stack_started": False,
        "auth_verified_after_restore": False,
        "session_history_verified": False,
        "superseded_memory_excluded": False,
        "retry_idempotency_verified": False,
    }

    # Step 1: Create state on live stack
    with Stack(live_stack_dir) as live:
        results["live_creation"] = True
        with httpx.Client(base_url=live.url, timeout=60, trust_env=False) as client:
            creds = {"username": f"synth_{secrets.token_hex(6)}", "password": secrets.token_urlsafe(20)}
            r_reg = client.post("/v1/auth/register", json=creds)
            assert r_reg.status_code == 201
            r_log = client.post("/v1/auth/login", json=creds)
            assert r_log.status_code == 200
            token = r_log.json()["token"]
            headers = {"Authorization": f"Bearer {token}"}

            r_sid = client.post("/v1/sessions", json={"title": "Pre-Backup Session"}, headers=headers)
            assert r_sid.status_code == 201
            session_id = r_sid.json()["session_id"]

            # Save initial memory (PostgreSQL)
            r_m1 = client.post("/v1/chat", json={
                "session_id": session_id,
                "message": "Hãy nhớ rằng chúng tôi chọn PostgreSQL cho cơ sở dữ liệu.",
                "request_id": "req_initial_db",
            }, headers=headers)
            assert r_m1.status_code == 200 and r_m1.json()["intent"] == "memory_create"

            # Supersede memory (PostgreSQL -> MongoDB)
            r_prop = client.post("/v1/chat", json={
                "session_id": session_id,
                "message": "Đổi PostgreSQL sang MongoDB nhé",
            }, headers=headers)
            assert r_prop.status_code == 200 and r_prop.json()["next_action"] == "await_confirm"

            r_conf = client.post("/v1/chat", json={
                "session_id": session_id,
                "message": "Đồng ý",
                "request_id": "req_confirm_supersede",
            }, headers=headers)
            assert r_conf.status_code == 200 and r_conf.json()["intent"] == "decision_update"

            # Perform online backup using SQLite Backup API while service is actively running
            ai_data_dir = live_stack_dir / "ai"
            for db_name in ("auth.db", "memory.db"):
                src_path = ai_data_dir / db_name
                dst_path = backup_dir / db_name
                with sqlite3.connect(f"file:{src_path.as_posix()}?mode=ro", uri=True) as src_conn:
                    with sqlite3.connect(dst_path.as_posix()) as dst_conn:
                        src_conn.backup(dst_conn)
                        assert dst_conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

            results["sqlite_backup_api_used"] = True
            results["backup_integrity_checked"] = True

    # Step 2: Restore into a completely new stack directory
    restored = Stack(restore_stack_dir)
    (restored.directory / "ai").mkdir(parents=True, exist_ok=True)
    for db_name in ("auth.db", "memory.db"):
        shutil.copy2(backup_dir / db_name, restored.directory / "ai" / db_name)

    # Verify integrity of restored files
    for db_name in ("auth.db", "memory.db"):
        with sqlite3.connect(restored.directory / "ai" / db_name) as conn:
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

    # Step 3: Boot a fresh Stack on the restored data
    with restored:
        results["restored_stack_started"] = True
        with httpx.Client(base_url=restored.url, timeout=60, trust_env=False) as client:
            # Login with original credentials
            r_log2 = client.post("/v1/auth/login", json=creds)
            assert r_log2.status_code == 200
            token2 = r_log2.json()["token"]
            headers2 = {"Authorization": f"Bearer {token2}"}
            results["auth_verified_after_restore"] = True

            # Verify session history survived restore
            r_msgs = client.get(f"/v1/sessions/{session_id}/messages", headers=headers2)
            assert r_msgs.status_code == 200 and len(r_msgs.json()) >= 3
            results["session_history_verified"] = True

            # Verify memory recall: only active fact (MongoDB) is returned, superseded (PostgreSQL) is excluded
            r_recall = client.post("/v1/chat", json={
                "session_id": session_id,
                "message": "Cơ sở dữ liệu được chọn là gì?",
            }, headers=headers2)
            assert r_recall.status_code == 200
            reply = r_recall.json()["reply"]
            assert "MongoDB" in reply and "PostgreSQL" not in reply
            assert r_recall.json()["response_source"] == "grounded_template"
            results["superseded_memory_excluded"] = True

            # Verify retry idempotency: resend the confirm request with original request_id
            state_before = client.get("/v1/me/state", headers=headers2).json()
            msgs_before_count = len(client.get(f"/v1/sessions/{session_id}/messages", headers=headers2).json())

            r_retry = client.post("/v1/chat", json={
                "session_id": session_id,
                "message": "Đồng ý",
                "request_id": "req_confirm_supersede",
                "is_retry": True,
            }, headers=headers2)
            assert r_retry.status_code == 200
            assert r_retry.json()["replayed"] is True
            assert r_retry.json()["response_source"] == "replay"

            state_after = client.get("/v1/me/state", headers=headers2).json()
            msgs_after_count = len(client.get(f"/v1/sessions/{session_id}/messages", headers=headers2).json())

            assert state_before == state_after
            assert msgs_before_count == msgs_after_count
            results["retry_idempotency_verified"] = True

    results["status"] = "passed"
    return results


def verify_protected_backup_integrity(protected_dir: Path) -> dict:
    """Level 2: Non-invasive, read-only integrity and schema check on protected backup files."""
    results = {
        "protected_dir": str(protected_dir),
        "databases": {},
        "integrity_passed": True,
    }

    if not protected_dir.is_dir():
        return {"status": "skipped", "reason": "protected_dir_not_found"}

    for db_name in ("auth.db", "memory.db"):
        db_file = protected_dir / db_name
        if not db_file.is_file():
            results["databases"][db_name] = {"present": False}
            results["integrity_passed"] = False
            continue

        conn = sqlite3.connect(f"file:{db_file.as_posix()}?mode=ro", uri=True)
        try:
            j_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            check = conn.execute("PRAGMA integrity_check").fetchone()[0]
            tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]

            # Count rows per table safely (no private content printed)
            table_counts = {}
            for t in tables:
                if not t.startswith("sqlite_"):
                    count = conn.execute(f"SELECT COUNT(*) FROM [{t}]").fetchone()[0]
                    table_counts[t] = count

            db_ok = (check == "ok")
            if not db_ok:
                results["integrity_passed"] = False

            results["databases"][db_name] = {
                "present": True,
                "journal_mode": j_mode,
                "integrity_check": check,
                "table_counts": table_counts,
                "status": "ok" if db_ok else "corrupt",
            }
        finally:
            conn.close()

    return results


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-dir", default="runtime/sqlite-backup-restore")
    p.add_argument("--protected-dir", default="backup-data-protected")
    args = p.parse_args()

    out = Path(args.output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "level1_synthetic_backup_restore": verify_synthetic_backup_restore(out),
        "level2_protected_backup_integrity": verify_protected_backup_integrity(Path(args.protected_dir).resolve()),
    }
    report["status"] = (
        "passed"
        if report["level1_synthetic_backup_restore"]["status"] == "passed"
        and report["level2_protected_backup_integrity"]["integrity_passed"]
        else "failed"
    )

    (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    sys.exit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
