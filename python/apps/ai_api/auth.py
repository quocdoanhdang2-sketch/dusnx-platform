"""
DUSN-X Authentication Module
- SQLite-backed user store (no plaintext passwords)
- SHA-256 + salt password hashing (no bcrypt dependency needed for Week 1)
- JWT-style opaque tokens with expiry stored in DB
- Used by FastAPI endpoints and proxied through Gateway
"""
from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# Support both DUSNX_TOKEN_TTL_HOURS and DUSNX_TOKEN_TTL_SECONDS
_ttl_sec = os.getenv("DUSNX_TOKEN_TTL_SECONDS")
if _ttl_sec is not None:
    TOKEN_TTL_HOURS = max(1, int(_ttl_sec) // 3600)
else:
    TOKEN_TTL_HOURS = int(os.getenv("DUSNX_TOKEN_TTL_HOURS", "24"))


def _get_db_path() -> Path:
    """Compute DB path at call time so env-var changes (e.g. in tests) are picked up."""
    return Path(os.getenv("DUSNX_DATA_DIR", "data")) / "auth.db"


def _get_conn(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def _init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tokens (
            token TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        );
        CREATE INDEX IF NOT EXISTS idx_tokens_user ON tokens(user_id);
        CREATE INDEX IF NOT EXISTS idx_tokens_expires ON tokens(expires_at);
    """)
    conn.commit()


import threading


def _hash_password(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


class AuthDB:
    """Thread-safe auth database wrapper."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._db_path = _get_db_path()
        self._conn = _get_conn(self._db_path)
        with self._lock:
            _init_db(self._conn)

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass

    def __del__(self) -> None:
        self.close()

    def register(self, username: str, password: str) -> dict:
        """Register a new user. Returns user info dict or raises ValueError."""
        username = username.strip().lower()
        if not username or len(username) < 3:
            raise ValueError("username must be at least 3 characters")
        if not password or len(password) < 8:
            raise ValueError("password must be at least 8 characters")
        salt = secrets.token_hex(16)
        pw_hash = _hash_password(password, salt)
        user_id = secrets.token_hex(16)
        created_at = datetime.now(timezone.utc).isoformat()
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT INTO users(user_id, username, password_hash, salt, created_at) VALUES(?,?,?,?,?)",
                    (user_id, username, pw_hash, salt, created_at),
                )
                self._conn.commit()
            except sqlite3.IntegrityError:
                raise ValueError(f"Username '{username}' already exists")
        return {"user_id": user_id, "username": username, "created_at": created_at}

    def login(self, username: str, password: str) -> Optional[str]:
        """Login and return a session token, or None if invalid."""
        username = username.strip().lower()
        with self._lock:
            row = self._conn.execute(
                "SELECT user_id, password_hash, salt FROM users WHERE username=?", (username,)
            ).fetchone()
            if row is None:
                return None
            pw_hash = _hash_password(password, row["salt"])
            if not secrets.compare_digest(pw_hash, row["password_hash"]):
                return None
            token = secrets.token_hex(32)
            expires_at = (datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS)).isoformat()
            self._conn.execute(
                "INSERT INTO tokens(token, user_id, expires_at) VALUES(?,?,?)",
                (token, row["user_id"], expires_at),
            )
            # Prune old tokens for this user (keep last 10)
            self._conn.execute(
                """DELETE FROM tokens WHERE user_id=? AND token NOT IN (
                    SELECT token FROM tokens WHERE user_id=? ORDER BY expires_at DESC LIMIT 10
                )""",
                (row["user_id"], row["user_id"]),
            )
            self._conn.commit()
            return token

    def logout(self, token: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM tokens WHERE token=?", (token,))
            self._conn.commit()

    def verify_token(self, token: str) -> Optional[dict]:
        """Return user info if token is valid, else None."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            row = self._conn.execute(
                """SELECT u.user_id, u.username FROM tokens t
                   JOIN users u ON t.user_id=u.user_id
                   WHERE t.token=? AND t.expires_at > ?""",
                (token, now),
            ).fetchone()
            if row is None:
                return None
            return {"user_id": row["user_id"], "username": row["username"]}

    def get_user_by_id(self, user_id: str) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                "SELECT user_id, username, created_at FROM users WHERE user_id=?", (user_id,)
            ).fetchone()
            return dict(row) if row else None


# Singleton
_auth_db: Optional[AuthDB] = None


def get_auth_db() -> AuthDB:
    global _auth_db
    if _auth_db is None:
        _auth_db = AuthDB()
    return _auth_db
