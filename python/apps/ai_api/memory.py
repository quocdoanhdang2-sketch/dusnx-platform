"""
DUSN-X Memory Module
- SQLite-backed personal memory store
- Supports read, create, update (supersede), delete
- Versioning: each update creates a new record and marks old one as superseded
- project-scoped memories
- User isolation enforced at DB layer
"""
from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import sqlite3


def _get_db_path() -> Path:
    """Compute DB path at call time so env-var changes (e.g. in tests) are picked up."""
    return Path(os.getenv("DUSNX_DATA_DIR", "data")) / "memory.db"


def _get_conn(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS memories (
            memory_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            info_type TEXT NOT NULL,
            content TEXT NOT NULL,
            source_event TEXT,
            source_session TEXT,
            project_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            version INTEGER NOT NULL DEFAULT 1,
            is_active INTEGER NOT NULL DEFAULT 1,
            superseded_by TEXT,
            FOREIGN KEY(superseded_by) REFERENCES memories(memory_id)
        );
        CREATE TABLE IF NOT EXISTS projects (
            project_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS chat_sessions (
            session_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS chat_messages (
            message_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            memory_ids_used TEXT,
            state_version INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY(session_id) REFERENCES chat_sessions(session_id)
        );
        CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id);
        CREATE INDEX IF NOT EXISTS idx_memories_user_active ON memories(user_id, is_active);
        CREATE INDEX IF NOT EXISTS idx_memories_project ON memories(project_id);
        CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_user ON chat_sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_messages_session ON chat_messages(session_id);
    """)
    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_memory(row: sqlite3.Row) -> dict:
    return {
        "memory_id": row["memory_id"],
        "user_id": row["user_id"],
        "info_type": row["info_type"],
        "content": row["content"],
        "source_event": row["source_event"],
        "source_session": row["source_session"],
        "project_id": row["project_id"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "version": row["version"],
        "is_active": bool(row["is_active"]),
        "superseded_by": row["superseded_by"],
    }


class MemoryDB:
    """Thread-safe memory database."""

    def __init__(self) -> None:
        self._db_path = _get_db_path()
        self._conn = _get_conn(self._db_path)
        _init_db(self._conn)

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def __del__(self) -> None:
        self.close()

    # ── Memory CRUD ────────────────────────────────────────────────────────────

    def create_memory(
        self,
        user_id: str,
        info_type: str,
        content: str,
        source_event: Optional[str] = None,
        source_session: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> dict:
        memory_id = secrets.token_hex(16)
        now = _now()
        self._conn.execute(
            """INSERT INTO memories(memory_id, user_id, info_type, content,
               source_event, source_session, project_id, created_at, updated_at,
               version, is_active) VALUES(?,?,?,?,?,?,?,?,?,1,1)""",
            (memory_id, user_id, info_type, content, source_event, source_session, project_id, now, now),
        )
        self._conn.commit()
        return self.get_memory(user_id, memory_id)

    def get_memory(self, user_id: str, memory_id: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM memories WHERE memory_id=? AND user_id=?", (memory_id, user_id)
        ).fetchone()
        return _row_to_memory(row) if row else None

    def list_memories(
        self,
        user_id: str,
        project_id: Optional[str] = None,
        include_inactive: bool = False,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        query = "SELECT * FROM memories WHERE user_id=?"
        params: list[Any] = [user_id]
        if not include_inactive:
            query += " AND is_active=1"
        if project_id is not None:
            query += " AND project_id=?"
            params.append(project_id)
        if search:
            query += " AND (content LIKE ? OR info_type LIKE ?)"
            like = f"%{search}%"
            params.extend([like, like])
        query += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self._conn.execute(query, params).fetchall()
        return [_row_to_memory(r) for r in rows]

    def update_memory(
        self,
        user_id: str,
        memory_id: str,
        new_content: str,
        new_type: Optional[str] = None,
        source_session: Optional[str] = None,
    ) -> Optional[dict]:
        """Supersede old memory and create a new version. Returns new memory."""
        old = self.get_memory(user_id, memory_id)
        if old is None:
            return None
        new_id = secrets.token_hex(16)
        now = _now()
        new_type = new_type or old["info_type"]
        # Create new version
        self._conn.execute(
            """INSERT INTO memories(memory_id, user_id, info_type, content,
               source_event, source_session, project_id, created_at, updated_at,
               version, is_active) VALUES(?,?,?,?,?,?,?,?,?,?,1)""",
            (new_id, user_id, new_type, new_content,
             old["source_event"], source_session or old["source_session"],
             old["project_id"], old["created_at"], now, old["version"] + 1),
        )
        # Deactivate old version and link to new
        self._conn.execute(
            "UPDATE memories SET is_active=0, superseded_by=?, updated_at=? WHERE memory_id=? AND user_id=?",
            (new_id, now, memory_id, user_id),
        )
        self._conn.commit()
        return self.get_memory(user_id, new_id)

    def get_memory_history(self, user_id: str, memory_id: str) -> list[dict]:
        """Get full version history for a memory chain (oldest to newest)."""
        target = self.get_memory(user_id, memory_id)
        if target is None:
            return []
        rows = self._conn.execute(
            "SELECT * FROM memories WHERE user_id=? AND created_at=? ORDER BY version ASC",
            (user_id, target["created_at"]),
        ).fetchall()
        return [_row_to_memory(r) for r in rows]

    def delete_memory(self, user_id: str, memory_id: str) -> bool:
        """Soft-delete: deactivate without removing the audit trail."""
        now = _now()
        cur = self._conn.execute(
            "UPDATE memories SET is_active=0, updated_at=? WHERE memory_id=? AND user_id=? AND is_active=1",
            (now, memory_id, user_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def get_active_memories_for_context(self, user_id: str, project_id: Optional[str] = None, limit: int = 20) -> list[dict]:
        """Get active memories to include in AI context."""
        return self.list_memories(user_id, project_id=project_id, include_inactive=False, limit=limit)

    # ── Project CRUD ───────────────────────────────────────────────────────────

    def create_project(self, user_id: str, name: str, description: str = "") -> dict:
        project_id = secrets.token_hex(16)
        now = _now()
        self._conn.execute(
            "INSERT INTO projects(project_id, user_id, name, description, created_at, updated_at) VALUES(?,?,?,?,?,?)",
            (project_id, user_id, name.strip(), description.strip(), now, now),
        )
        self._conn.commit()
        return self.get_project(user_id, project_id)

    def get_project(self, user_id: str, project_id: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM projects WHERE project_id=? AND user_id=?", (project_id, user_id)
        ).fetchone()
        return dict(row) if row else None

    def list_projects(self, user_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM projects WHERE user_id=? AND is_active=1 ORDER BY updated_at DESC", (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ── Chat Session CRUD ──────────────────────────────────────────────────────

    def create_session(self, user_id: str, title: Optional[str] = None) -> dict:
        session_id = secrets.token_hex(16)
        now = _now()
        self._conn.execute(
            "INSERT INTO chat_sessions(session_id, user_id, title, created_at, updated_at) VALUES(?,?,?,?,?)",
            (session_id, user_id, title or "Phiên chat mới", now, now),
        )
        self._conn.commit()
        return {"session_id": session_id, "user_id": user_id, "title": title or "Phiên chat mới",
                "created_at": now, "updated_at": now}

    def get_session(self, user_id: str, session_id: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM chat_sessions WHERE session_id=? AND user_id=?", (session_id, user_id)
        ).fetchone()
        return dict(row) if row else None

    def list_sessions(self, user_id: str, limit: int = 50) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM chat_sessions WHERE user_id=? ORDER BY updated_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_session_title(self, user_id: str, session_id: str, title: str) -> None:
        self._conn.execute(
            "UPDATE chat_sessions SET title=?, updated_at=? WHERE session_id=? AND user_id=?",
            (title, _now(), session_id, user_id),
        )
        self._conn.commit()

    def delete_session(self, user_id: str, session_id: str) -> bool:
        cur = self._conn.execute(
            "DELETE FROM chat_sessions WHERE session_id=? AND user_id=?",
            (session_id, user_id),
        )
        self._conn.execute(
            "DELETE FROM chat_messages WHERE session_id=? AND user_id=?",
            (session_id, user_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def _touch_session(self, user_id: str, session_id: str) -> None:
        self._conn.execute(
            "UPDATE chat_sessions SET updated_at=? WHERE session_id=? AND user_id=?",
            (_now(), session_id, user_id),
        )

    # ── Chat Message CRUD ──────────────────────────────────────────────────────

    def append_message(
        self,
        session_id: str,
        user_id: str,
        role: str,
        content: str,
        memory_ids_used: Optional[list[str]] = None,
        state_version: Optional[int] = None,
    ) -> dict:
        message_id = secrets.token_hex(16)
        now = _now()
        self._conn.execute(
            """INSERT INTO chat_messages(message_id, session_id, user_id, role, content,
               memory_ids_used, state_version, created_at) VALUES(?,?,?,?,?,?,?,?)""",
            (
                message_id, session_id, user_id, role, content,
                json.dumps(memory_ids_used or []),
                state_version, now,
            ),
        )
        self._touch_session(user_id, session_id)
        self._conn.commit()
        return {
            "message_id": message_id, "session_id": session_id, "user_id": user_id,
            "role": role, "content": content,
            "memory_ids_used": memory_ids_used or [],
            "state_version": state_version,
            "created_at": now,
        }

    def get_messages(self, user_id: str, session_id: str, limit: int = 100, offset: int = 0) -> list[dict]:
        rows = self._conn.execute(
            """SELECT * FROM chat_messages WHERE session_id=? AND user_id=?
               ORDER BY created_at ASC LIMIT ? OFFSET ?""",
            (session_id, user_id, limit, offset),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["memory_ids_used"] = json.loads(d["memory_ids_used"] or "[]")
            except Exception:
                d["memory_ids_used"] = []
            result.append(d)
        return result


# Singleton
_memory_db: Optional[MemoryDB] = None


def get_memory_db() -> MemoryDB:
    global _memory_db
    if _memory_db is None:
        _memory_db = MemoryDB()
    return _memory_db
