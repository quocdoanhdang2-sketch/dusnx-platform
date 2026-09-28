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
import re
import secrets
import threading
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
        -- Persistent DUSN-X vector state per user (survives restarts, cross-session)
        CREATE TABLE IF NOT EXISTS dusnx_state (
            user_id TEXT PRIMARY KEY,
            state_blob TEXT NOT NULL,
            state_version INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );
        -- Pending decision modification requests (awaiting user confirmation)
        CREATE TABLE IF NOT EXISTS pending_decision_updates (
            pending_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            old_memory_id TEXT NOT NULL,
            old_content TEXT NOT NULL,
            proposed_content TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'awaiting_confirm',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        -- Authenticated timeline events per user (unified state / cross-client event store)
        CREATE TABLE IF NOT EXISTS user_events (
            event_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            platform TEXT NOT NULL,
            event_type TEXT NOT NULL,
            content TEXT NOT NULL,
            project_id TEXT,
            feedback_value REAL NOT NULL DEFAULT 0.0,
            event_time_utc TEXT NOT NULL,
            provenance TEXT NOT NULL,
            state_version INTEGER NOT NULL,
            intent TEXT,
            selected_agent TEXT,
            next_action TEXT,
            confidence REAL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id);
        CREATE INDEX IF NOT EXISTS idx_memories_user_active ON memories(user_id, is_active);
        CREATE INDEX IF NOT EXISTS idx_memories_project ON memories(project_id);
        CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id);
        CREATE INDEX IF NOT EXISTS idx_sessions_user ON chat_sessions(user_id);
        CREATE INDEX IF NOT EXISTS idx_messages_session ON chat_messages(session_id);
        CREATE INDEX IF NOT EXISTS idx_pending_user ON pending_decision_updates(user_id);
        CREATE INDEX IF NOT EXISTS idx_user_events_user_time ON user_events(user_id, event_time_utc DESC);
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
        self._lock = threading.RLock()
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
        with self._lock:
            self._conn.execute(
                """INSERT INTO memories(memory_id, user_id, info_type, content,
                   source_event, source_session, project_id, created_at, updated_at,
                   version, is_active) VALUES(?,?,?,?,?,?,?,?,?,1,1)""",
                (memory_id, user_id, info_type, content, source_event, source_session, project_id, now, now),
            )
            self._conn.commit()
            return self.get_memory(user_id, memory_id)

    def get_memory(self, user_id: str, memory_id: str) -> Optional[dict]:
        with self._lock:
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
        with self._lock:
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
        with self._lock:
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
        with self._lock:
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
        with self._lock:
            cur = self._conn.execute(
                "UPDATE memories SET is_active=0, updated_at=? WHERE memory_id=? AND user_id=? AND is_active=1",
                (now, memory_id, user_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def get_active_memories_for_context(
        self,
        user_id: str,
        project_id: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 15,
    ) -> list[dict]:
        """
        Explainable selection of active memories for context:
        - Strict project scoping:
          - If project_id provided: include global memories (project_id IS NULL or '') AND matching project memories.
            Never leak other projects' memories!
          - If project_id NOT provided: only include global memories (project_id IS NULL or '').
            Never leak project-scoped memories into general chat!
        - Relevance scoring:
          - Query token overlap with memory content.
          - Type weighting: decision (1.5x), preference (1.3x), goal (1.2x), other (1.0x).
          - Exact project match bonus (+2.0).
          - Recency boost.
        """
        with self._lock:
            if project_id:
                query_sql = """
                    SELECT * FROM memories
                    WHERE user_id=? AND is_active=1
                      AND (project_id=? OR project_id IS NULL OR project_id='')
                    ORDER BY updated_at DESC
                """
                rows = self._conn.execute(query_sql, (user_id, project_id)).fetchall()
            else:
                query_sql = """
                    SELECT * FROM memories
                    WHERE user_id=? AND is_active=1
                      AND (project_id IS NULL OR project_id='')
                    ORDER BY updated_at DESC
                """
                rows = self._conn.execute(query_sql, (user_id,)).fetchall()

        all_active = [_row_to_memory(r) for r in rows]
        if not query or not all_active:
            return all_active[:limit]

        q_tokens = set(re.findall(r"\w+", query.lower(), flags=re.UNICODE))

        def score_memory(mem: dict) -> float:
            content_tokens = set(re.findall(r"\w+", mem["content"].lower(), flags=re.UNICODE))
            overlap = len(q_tokens & content_tokens)
            type_weight = {
                "decision": 1.5,
                "preference": 1.3,
                "goal": 1.2,
            }.get(mem.get("info_type", ""), 1.0)
            score = overlap * type_weight
            if project_id and mem.get("project_id") == project_id:
                score += 2.0
            score += min(mem.get("version", 1) * 0.1, 0.5)
            return score

        scored = [(score_memory(m), m) for m in all_active]
        scored.sort(key=lambda x: (x[0], x[1]["updated_at"]), reverse=True)
        return [m for _, m in scored[:limit]]

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


    # ── DUSN-X Persistent State ────────────────────────────────────────────────

    def get_dusnx_state(self, user_id: str) -> Optional[dict]:
        """Return stored state blob for a user, or None if first time."""
        row = self._conn.execute(
            "SELECT state_blob, state_version, updated_at FROM dusnx_state WHERE user_id=?",
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "state_blob": json.loads(row["state_blob"]),
            "state_version": row["state_version"],
            "updated_at": row["updated_at"],
        }

    def set_dusnx_state(self, user_id: str, state_blob: dict, state_version: int) -> None:
        """Upsert DUSN-X state for a user (INSERT OR REPLACE)."""
        now = _now()
        self._conn.execute(
            """INSERT INTO dusnx_state(user_id, state_blob, state_version, updated_at)
               VALUES(?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET
                   state_blob=excluded.state_blob,
                   state_version=excluded.state_version,
                   updated_at=excluded.updated_at""",
            (user_id, json.dumps(state_blob), state_version, now),
        )
        self._conn.commit()

    # ── Pending Decision Modification ──────────────────────────────────────────

    def create_pending_decision(
        self,
        user_id: str,
        session_id: str,
        old_memory_id: str,
        old_content: str,
        proposed_content: str,
    ) -> dict:
        """Create a pending decision update request awaiting user confirmation."""
        pending_id = secrets.token_hex(12)
        now = _now()
        self._conn.execute(
            """INSERT INTO pending_decision_updates(
                   pending_id, user_id, session_id, old_memory_id, old_content,
                   proposed_content, status, created_at, updated_at)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (pending_id, user_id, session_id, old_memory_id, old_content,
             proposed_content, "awaiting_confirm", now, now),
        )
        self._conn.commit()
        return self.get_pending_decision(user_id, pending_id)  # type: ignore[return-value]

    def get_pending_decision(self, user_id: str, pending_id: str) -> Optional[dict]:
        row = self._conn.execute(
            "SELECT * FROM pending_decision_updates WHERE pending_id=? AND user_id=?",
            (pending_id, user_id),
        ).fetchone()
        return dict(row) if row else None

    def get_session_pending_decision(self, user_id: str, session_id: str) -> Optional[dict]:
        """Return the most recent awaiting_confirm pending decision for a session."""
        row = self._conn.execute(
            """SELECT * FROM pending_decision_updates
               WHERE user_id=? AND session_id=? AND status='awaiting_confirm'
               ORDER BY created_at DESC LIMIT 1""",
            (user_id, session_id),
        ).fetchone()
        return dict(row) if row else None

    def resolve_pending_decision_atomic(
        self,
        user_id: str,
        pending_id: str,
        accepted: bool,
        source_session: Optional[str] = None,
    ) -> dict:
        """
        Atomically confirm or reject a pending decision update in a single transaction.
        If accepted:
          - Verifies pending record exists for user_id and status is 'awaiting_confirm'.
          - Verifies old memory exists, belongs to user_id, and is active (is_active=1).
          - If old memory is inactive, marks pending status as 'stale' and aborts without modification.
          - Updates pending record to 'confirmed'.
          - Inserts new memory version with incremented version number.
          - Deactivates old memory (is_active=0, superseded_by=new_id).
          - All DB updates are executed in a single atomic transaction; any failure triggers rollback.
        If rejected:
          - Marks pending record as 'rejected'.
          - Old memory is left completely untouched.
        Returns:
          dict with success boolean, status, pending, and new_memory (if confirmed).
        """
        now = _now()
        if not accepted:
            with self._conn:
                row = self._conn.execute(
                    "SELECT * FROM pending_decision_updates WHERE pending_id=? AND user_id=?",
                    (pending_id, user_id),
                ).fetchone()
                if row is None:
                    return {"success": False, "error": "not_found", "detail": "Pending decision not found"}
                if row["status"] != "awaiting_confirm":
                    return {
                        "success": False,
                        "error": f"already_{row['status']}",
                        "detail": f"Pending decision is already {row['status']}",
                        "pending": dict(row),
                    }
                cur = self._conn.execute(
                    """UPDATE pending_decision_updates SET status='rejected', updated_at=?
                       WHERE pending_id=? AND user_id=? AND status='awaiting_confirm'""",
                    (now, pending_id, user_id),
                )
                if cur.rowcount == 0:
                    return {"success": False, "error": "conflict", "detail": "Concurrent conflict"}
                updated_pending = self.get_pending_decision(user_id, pending_id)
                return {"success": True, "status": "rejected", "pending": updated_pending}

        # accepted is True: single atomic transaction
        with self._conn:
            row = self._conn.execute(
                "SELECT * FROM pending_decision_updates WHERE pending_id=? AND user_id=?",
                (pending_id, user_id),
            ).fetchone()
            if row is None:
                return {"success": False, "error": "not_found", "detail": "Pending decision not found"}
            if row["status"] != "awaiting_confirm":
                return {
                    "success": False,
                    "error": f"already_{row['status']}",
                    "detail": f"Pending decision is already {row['status']}",
                    "pending": dict(row),
                }

            # Verify old memory is still active and belongs to user
            old_mem = self._conn.execute(
                "SELECT * FROM memories WHERE memory_id=? AND user_id=?",
                (row["old_memory_id"], user_id),
            ).fetchone()
            if old_mem is None or not old_mem["is_active"]:
                self._conn.execute(
                    """UPDATE pending_decision_updates SET status='stale', updated_at=?
                       WHERE pending_id=? AND user_id=?""",
                    (now, pending_id, user_id),
                )
                return {
                    "success": False,
                    "error": "stale_memory",
                    "detail": "Quyết định cũ không còn hiệu lực hoặc đã bị thay đổi trước đó",
                    "pending": self.get_pending_decision(user_id, pending_id),
                }

            # Update pending status to confirmed
            cur_p = self._conn.execute(
                """UPDATE pending_decision_updates SET status='confirmed', updated_at=?
                   WHERE pending_id=? AND user_id=? AND status='awaiting_confirm'""",
                (now, pending_id, user_id),
            )
            if cur_p.rowcount == 0:
                return {"success": False, "error": "conflict", "detail": "Concurrent conflict"}

            # Insert new memory version
            new_id = secrets.token_hex(16)
            new_type = old_mem["info_type"]
            new_content = row["proposed_content"]
            eff_session = source_session or row["session_id"] or old_mem["source_session"]
            self._conn.execute(
                """INSERT INTO memories(memory_id, user_id, info_type, content,
                   source_event, source_session, project_id, created_at, updated_at,
                   version, is_active) VALUES(?,?,?,?,?,?,?,?,?,?,1)""",
                (new_id, user_id, new_type, new_content,
                 old_mem["source_event"], eff_session,
                 old_mem["project_id"], old_mem["created_at"], now, old_mem["version"] + 1),
            )

            # Deactivate old memory
            cur_m = self._conn.execute(
                """UPDATE memories SET is_active=0, superseded_by=?, updated_at=?
                   WHERE memory_id=? AND user_id=? AND is_active=1""",
                (new_id, now, row["old_memory_id"], user_id),
            )
            if cur_m.rowcount == 0:
                raise sqlite3.OperationalError("Failed to deactivate old active memory atomically")

            new_mem = self.get_memory(user_id, new_id)
            updated_pending = self.get_pending_decision(user_id, pending_id)
            return {
                "success": True,
                "status": "confirmed",
                "pending": updated_pending,
                "new_memory": new_mem,
                "old_memory_id": row["old_memory_id"],
            }

    def resolve_pending_decision(
        self,
        user_id: str,
        pending_id: str,
        accepted: bool,
    ) -> Optional[dict]:
        """Mark pending decision as confirmed or rejected. Returns updated record."""
        res = self.resolve_pending_decision_atomic(user_id, pending_id, accepted)
        return res.get("pending") if res["success"] else None

    # ── Authenticated User Events (Timeline & Cross-Client State) ──────────────

    def record_user_event(
        self,
        user_id: str,
        platform: str,
        event_type: str,
        content: str,
        project_id: Optional[str] = None,
        feedback_value: float = 0.0,
        event_id: Optional[str] = None,
        event_time_utc: Optional[str] = None,
        provenance: Optional[str] = None,
        state_version: int = 1,
        intent: Optional[str] = None,
        selected_agent: Optional[str] = None,
        next_action: Optional[str] = None,
        confidence: Optional[float] = None,
    ) -> dict:
        """
        Record an event for an authenticated user with deduplication & provenance.
        Returns a dict representing the event, with 'duplicate': True/False.
        """
        now = _now()
        event_time = event_time_utc or now
        source_prov = provenance or f"client:{platform}"
        eff_event_id = event_id.strip() if event_id and event_id.strip() else secrets.token_hex(16)

        with self._lock:
            # Check deduplication
            existing = self._conn.execute(
                "SELECT * FROM user_events WHERE event_id=?", (eff_event_id,)
            ).fetchone()
            if existing is not None:
                if existing["user_id"] != user_id:
                    raise PermissionError("Event ID belongs to another user")
                res = dict(existing)
                res["duplicate"] = True
                return res

            self._conn.execute(
                """INSERT INTO user_events(
                       event_id, user_id, platform, event_type, content, project_id,
                       feedback_value, event_time_utc, provenance, state_version,
                       intent, selected_agent, next_action, confidence, created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    eff_event_id, user_id, platform.lower().strip(), event_type.strip(),
                    content.strip(), project_id, float(feedback_value),
                    event_time, source_prov, int(state_version),
                    intent, selected_agent, next_action,
                    float(confidence) if confidence is not None else None,
                    now,
                ),
            )
            self._conn.commit()
            saved = self.get_user_event(user_id, eff_event_id)
            if saved is None:
                raise RuntimeError("Failed to retrieve saved user event")
            saved["duplicate"] = False
            return saved

    def get_user_event(self, user_id: str, event_id: str) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM user_events WHERE event_id=? AND user_id=?", (event_id, user_id)
            ).fetchone()
            return dict(row) if row else None

    def list_user_events(
        self,
        user_id: str,
        platform: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        before_time: Optional[str] = None,
    ) -> list[dict]:
        """List authenticated user events in reverse chronological order with optional platform filter and offset."""
        limit = max(1, min(limit, 100))
        offset = max(0, offset)
        query = "SELECT * FROM user_events WHERE user_id=?"
        params: list[Any] = [user_id]
        if platform:
            query += " AND platform = ?"
            params.append(platform)
        if before_time:
            query += " AND event_time_utc < ?"
            params.append(before_time)
        query += " ORDER BY event_time_utc DESC, created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]

    def get_last_user_event_time(self, user_id: str) -> Optional[str]:
        """Return ISO timestamp of the most recent event for this user."""
        with self._lock:
            row = self._conn.execute(
                "SELECT event_time_utc FROM user_events WHERE user_id=? ORDER BY event_time_utc DESC LIMIT 1",
                (user_id,),
            ).fetchone()
            return row["event_time_utc"] if row else None


# Singleton
_memory_db: Optional[MemoryDB] = None


def get_memory_db() -> MemoryDB:
    global _memory_db
    if _memory_db is None:
        _memory_db = MemoryDB()
    return _memory_db
