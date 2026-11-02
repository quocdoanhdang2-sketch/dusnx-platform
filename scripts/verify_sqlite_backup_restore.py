"""SQLite Backup and Restore Verification Harness.

Thực hiện kiểm chứng 2 mức độc lập:
1. Mức 1 (DB tổng hợp đầy đủ):
   - Tạo user, session, chuỗi lịch sử dài (>200 tin nhắn với thứ tự và ID xác định),
     active/superseded memory, receipt ID trên Stack đang chạy.
   - Backup bằng SQLite Backup API (src.backup(dst)) trong khi service đang hoạt động.
   - Kiểm tra PRAGMA integrity_check trên bản backup.
   - Khôi phục (restore) sang thư mục hoàn toàn mới.
   - Khởi động Stack mới trên dữ liệu khôi phục.
   - Xác minh auth hoạt động sau restore.
   - Đọc hết các trang lịch sử (cursor pagination), đối chiếu toàn bộ >200 tin nhắn
     khớp 100% ID và nội dung trước backup, không mất/trùng tin tại ranh giới trang.
   - Xác minh memory recall (chỉ trả về quyết định active mới, loại bỏ superseded cũ).
   - Xác minh tính bất biến của retry (idempotency replay, không tạo trùng mutation/tin nhắn/state).
2. Mức 2 (Dữ liệu bảo vệ / Backup cá nhân):
   - Kiểm tra an toàn ở chế độ chỉ đọc (read-only), không làm sập tiến trình nếu thư mục thiếu.
   - Kiểm tra tính toàn vẹn (PRAGMA integrity_check, journal_mode WAL).
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
        "long_history_restored_in_order": False,
        "total_messages_verified": 0,
        "pages_fetched": 0,
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
            me = client.get("/v1/auth/me", headers=headers).json()
            user_id = me["user_id"]

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

            # Create a dedicated long-history session with exactly 205 messages
            r_long = client.post("/v1/sessions", json={"title": "Long History 205 msgs"}, headers=headers)
            assert r_long.status_code == 201
            long_session_id = r_long.json()["session_id"]

            expected_history_contents = [f"synthetic-history-item-{i:03d}" for i in range(205)]
            expected_history_ids = [f"msg-{i:04d}" for i in range(205)]

            # Insert 205 deterministic messages directly into active SQLite WAL database
            ai_data_dir = live_stack_dir / "ai"
            with sqlite3.connect(ai_data_dir / "memory.db") as conn:
                conn.executemany(
                    "INSERT INTO chat_messages(message_id,session_id,user_id,role,content,"
                    "memory_ids_used,created_at) VALUES(?,?,?,?,?,?,?)",
                    [
                        (
                            expected_history_ids[i],
                            long_session_id,
                            user_id,
                            "user",
                            expected_history_contents[i],
                            "[]",
                            f"2026-11-02T10:{i // 60:02d}:{i % 60:02d}+00:00",
                        )
                        for i in range(205)
                    ],
                )

            # Perform online backup using SQLite Backup API while service is actively running
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

            # Verify cursor-based pagination over 205 messages across all pages without loss/duplicate
            collected_messages = []
            cursor = None
            pages_count = 0

            while True:
                url = f"/v1/sessions/{long_session_id}/messages/page?limit=100"
                if cursor:
                    url += f"&before={cursor}"
                r_page = client.get(url, headers=headers2)
                assert r_page.status_code == 200, f"Failed to get page: {r_page.text}"
                page_data = r_page.json()
                batch = page_data["messages"]
                pages_count += 1
                collected_messages = batch + collected_messages
                cursor = page_data.get("next_before")
                if not cursor:
                    break

            assert len(collected_messages) == 205, f"Expected 205 messages, got {len(collected_messages)}"
            assert [m["content"] for m in collected_messages] == expected_history_contents
            assert [m["message_id"] for m in collected_messages] == expected_history_ids
            assert pages_count == 3  # Page 1: 100 msgs, Page 2: 100 msgs, Page 3: 5 msgs

            results["long_history_restored_in_order"] = True
            results["total_messages_verified"] = len(collected_messages)
            results["pages_fetched"] = pages_count

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
        "status": "unverified",
        "databases": {},
        "integrity_passed": False,
    }

    if not protected_dir.is_dir():
        return {
            "protected_dir": str(protected_dir),
            "status": "skipped",
            "reason": "protected_dir_not_found",
            "integrity_passed": None,
            "databases": {},
        }

    all_ok = True
    for db_name in ("auth.db", "memory.db"):
        db_file = protected_dir / db_name
        if not db_file.is_file():
            results["databases"][db_name] = {"present": False}
            all_ok = False
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
                all_ok = False

            results["databases"][db_name] = {
                "present": True,
                "journal_mode": j_mode,
                "integrity_check": check,
                "table_counts": table_counts,
                "status": "ok" if db_ok else "corrupt",
            }
        finally:
            conn.close()

    results["integrity_passed"] = all_ok
    results["status"] = "passed" if all_ok else "failed"
    return results


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-dir", default="runtime/sqlite-backup-restore")
    p.add_argument("--protected-dir", default="backup-data-protected")
    p.add_argument("--require-protected", action="store_true", help="Fail if protected backup directory is missing")
    args = p.parse_args()

    out = Path(args.output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)

    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "level1_synthetic_backup_restore": verify_synthetic_backup_restore(out),
        "level2_protected_backup_integrity": verify_protected_backup_integrity(Path(args.protected_dir).resolve()),
    }

    lvl1_ok = (report["level1_synthetic_backup_restore"]["status"] == "passed")
    lvl2 = report["level2_protected_backup_integrity"]

    if lvl2.get("status") == "skipped":
        if args.require_protected:
            report["status"] = "failed"
            report["status_reason"] = "protected_backup_missing_and_required"
        else:
            report["status"] = "passed" if lvl1_ok else "failed"
            report["status_reason"] = "level1_verified_level2_skipped"
    else:
        report["status"] = "passed" if (lvl1_ok and lvl2.get("integrity_passed") is True) else "failed"
        report["status_reason"] = "level1_and_level2_verified"

    (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    sys.exit(0 if report["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
