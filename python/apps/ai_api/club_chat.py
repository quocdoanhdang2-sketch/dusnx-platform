"""Internal member messaging for the CLB app.

1-1 direct messages and per-unit groups ("Toàn CLB", "Ban kỹ thuật", ...).
Lives in its own SQLite file (club_chat.db) so it never touches memory.db or
the running DUSN-X chat tables. Authorization is enforced here; role checks
(owner/deputy/lead) are done by the caller via auth.verify_token.
"""
from __future__ import annotations

import os
import secrets
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _db_path() -> Path:
    return Path(os.getenv("DUSNX_DATA_DIR", "data")) / "club_chat.db"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ClubChatDB:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        path = _db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False, timeout=10)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS conversations (
                    conv_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,              -- 'dm' | 'group'
                    name TEXT,                       -- group name
                    unit TEXT,                       -- ban / 'toan-clb'
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conversation_members (
                    conv_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    can_pin INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(conv_id, user_id)
                );
                CREATE TABLE IF NOT EXISTS messages (
                    message_id TEXT PRIMARY KEY,
                    conv_id TEXT NOT NULL,
                    sender_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    pinned INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conv_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_msg_conv_id ON messages(conv_id, message_id);
            """)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass

    # -- conversation helpers ------------------------------------------------

    def _is_member(self, conv_id: str, user_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM conversation_members WHERE conv_id=? AND user_id=?",
            (conv_id, user_id)).fetchone()
        return row is not None

    def _require_member(self, conv_id: str, user_id: str) -> None:
        if not self._is_member(conv_id, user_id):
            raise PermissionError("not a member of this conversation")

    def create_dm(self, user_a: str, user_b: str) -> str:
        """Find or create the 1-1 conversation between two users."""
        if user_a == user_b:
            raise ValueError("cannot dm yourself")
        with self._lock, self._conn:
            row = self._conn.execute(
                """SELECT c.conv_id FROM conversations c
                   JOIN conversation_members m1 ON m1.conv_id=c.conv_id AND m1.user_id=?
                   JOIN conversation_members m2 ON m2.conv_id=c.conv_id AND m2.user_id=?
                   WHERE c.kind='dm'""", (user_a, user_b)).fetchone()
            if row:
                return row["conv_id"]
            conv_id = secrets.token_hex(12)
            self._conn.execute(
                "INSERT INTO conversations VALUES(?,?,?,?,?,?)",
                (conv_id, "dm", None, None, user_a, _now()))
            self._conn.executemany(
                "INSERT INTO conversation_members(conv_id, user_id) VALUES(?,?)",
                [(conv_id, user_a), (conv_id, user_b)])
            self._conn.commit()
            return conv_id

    def create_group(self, creator: str, name: str, unit: str,
                     members: list, creator_can_pin: bool = True) -> str:
        """Creator must be lead/owner/deputy — checked by the caller."""
        members = [m for m in dict.fromkeys(members) if m != creator]
        conv_id = secrets.token_hex(12)
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO conversations VALUES(?,?,?,?,?,?)",
                (conv_id, "group", name, unit, creator, _now()))
            rows = [(conv_id, creator, 1 if creator_can_pin else 0)]
            rows += [(conv_id, m, 0) for m in members]
            self._conn.executemany(
                "INSERT INTO conversation_members(conv_id, user_id, can_pin) VALUES(?,?,?)",
                rows)
            self._conn.commit()
            return conv_id

    def list_conversations(self, user_id: str) -> list:
        with self._lock:
            rows = self._conn.execute(
                """SELECT c.conv_id, c.kind, c.name, c.unit
                   FROM conversations c
                   JOIN conversation_members m ON m.conv_id=c.conv_id
                   WHERE m.user_id=? ORDER BY c.created_at""", (user_id,)).fetchall()
            return [dict(r) for r in rows]

    # -- messages ------------------------------------------------------------

    def send(self, conv_id: str, sender_id: str, content: str) -> dict:
        content = (content or "").strip()
        if not content:
            raise ValueError("empty message")
        if len(content) > 4000:
            raise ValueError("message too long (4000 chars)")
        with self._lock, self._conn:
            self._require_member(conv_id, sender_id)
            message_id = secrets.token_hex(12)
            created_at = _now()
            self._conn.execute(
                "INSERT INTO messages VALUES(?,?,?,?,0,?)",
                (message_id, conv_id, sender_id, content, created_at))
            self._conn.commit()
            return {"message_id": message_id, "conv_id": conv_id,
                    "sender_id": sender_id, "content": content,
                    "pinned": 0, "created_at": created_at}

    def list_messages(self, conv_id: str, user_id: str, after_id: Optional[str] = None,
                      limit: int = 50) -> list:
        with self._lock:
            self._require_member(conv_id, user_id)
            if after_id:
                anchor = self._conn.execute(
                    "SELECT created_at FROM messages WHERE message_id=?", (after_id,)).fetchone()
                if anchor is None:
                    return []
                rows = self._conn.execute(
                    """SELECT * FROM messages WHERE conv_id=? AND created_at>?
                       ORDER BY created_at LIMIT ?""",
                    (conv_id, anchor["created_at"], limit)).fetchall()
            else:
                rows = self._conn.execute(
                    """SELECT * FROM messages WHERE conv_id=? ORDER BY created_at DESC LIMIT ?""",
                    (conv_id, limit)).fetchall()
                rows = list(reversed(rows))
            return [dict(r) for r in rows]

    def pin_message(self, conv_id: str, user_id: str, message_id: str, pinned: bool = True) -> None:
        with self._lock, self._conn:
            self._require_member(conv_id, user_id)
            can_pin = self._conn.execute(
                "SELECT can_pin FROM conversation_members WHERE conv_id=? AND user_id=?",
                (conv_id, user_id)).fetchone()["can_pin"]
            if not can_pin:
                raise PermissionError("only managers can pin")
            cur = self._conn.execute(
                "UPDATE messages SET pinned=? WHERE conv_id=? AND message_id=?",
                (1 if pinned else 0, conv_id, message_id))
            if cur.rowcount == 0:
                raise ValueError("message not found")
            self._conn.commit()


_chat_db: Optional[ClubChatDB] = None


def get_club_chat_db() -> ClubChatDB:
    global _chat_db
    if _chat_db is None:
        _chat_db = ClubChatDB()
    return _chat_db
