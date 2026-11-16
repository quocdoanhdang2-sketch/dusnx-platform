"""
DUSN-X Authentication Module
- SQLite-backed user store (no plaintext passwords)
- Versioned scrypt password hashes; legacy SHA-256 upgraded on successful login
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
    TOKEN_TTL_HOURS = max(1, int(_ttl_sec)) / 3600
else:
    TOKEN_TTL_HOURS = int(os.getenv("DUSNX_TOKEN_TTL_HOURS", "24"))


# CLB roles: English keys, Vietnamese labels live client-side.
ROLES = ("owner", "deputy", "lead", "member")
STATUSES = ("pending", "approved")


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
            created_at TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'member',
            status TEXT NOT NULL DEFAULT 'approved',
            display_name TEXT
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
    _ensure_columns(conn)
    conn.commit()


def _ensure_columns(conn: sqlite3.Connection) -> None:
    """Additive migration for existing auth.db files: never drops data."""
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
    if "role" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'member'")
    if "status" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN status TEXT NOT NULL DEFAULT 'approved'")
    if "display_name" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN display_name TEXT")


import threading


def _hash_password(password: str, salt: str) -> str:
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt.encode("utf-8"),
                             n=16384, r=8, p=1, dklen=32)
    return "scrypt$16384$8$1$" + derived.hex()


def _verify_password(password: str, salt: str, stored: str) -> bool:
    if stored.startswith("scrypt$16384$8$1$"):
        return secrets.compare_digest(_hash_password(password, salt), stored)
    # Preserve existing accounts without rewriting their DB or password column.
    if len(stored) == 64:
        legacy = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
        return secrets.compare_digest(legacy, stored)
    return False


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

    def register(self, username: str, password: str, display_name: Optional[str] = None,
                 status: Optional[str] = None, role: str = "member") -> dict:
        """Register a new user. Returns user info dict or raises ValueError.

        Default status comes from DUSNX_DEFAULT_USER_STATUS ('pending' for the
        club app: a manager must approve before login; 'approved' elsewhere so
        legacy callers/tests keep instant login). Explicit status= overrides.
        """
        if status is None:
            status = os.getenv("DUSNX_DEFAULT_USER_STATUS", "approved")
        username = username.strip().lower()
        if not username or len(username) < 3:
            raise ValueError("username must be at least 3 characters")
        if not password or len(password) < 8:
            raise ValueError("password must be at least 8 characters")
        if role not in ROLES:
            raise ValueError(f"unknown role: {role}")
        if status not in STATUSES:
            raise ValueError(f"unknown status: {status}")
        salt = secrets.token_hex(16)
        pw_hash = _hash_password(password, salt)
        user_id = secrets.token_hex(16)
        created_at = datetime.now(timezone.utc).isoformat()
        with self._lock, self._conn:
            try:
                self._conn.execute(
                    """INSERT INTO users(user_id, username, password_hash, salt, created_at,
                                         role, status, display_name)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (user_id, username, pw_hash, salt, created_at, role, status, display_name),
                )
                self._conn.commit()
            except sqlite3.IntegrityError:
                raise ValueError(f"Username '{username}' already exists")
        return {"user_id": user_id, "username": username, "created_at": created_at,
                "role": role, "status": status, "display_name": display_name}

    def authenticate(self, username: str, password: str) -> Optional[dict]:
        """Verify credentials. Returns user info + token (token is None while
        the account is pending approval). Returns None for bad credentials."""
        username = username.strip().lower()
        with self._lock:
            row = self._conn.execute(
                """SELECT user_id, username, password_hash, salt, role, status, display_name
                   FROM users WHERE username=?""", (username,),
            ).fetchone()
            if row is None:
                return None
            if not _verify_password(password, row["salt"], row["password_hash"]):
                return None
            if not row["password_hash"].startswith("scrypt$"):
                self._conn.execute("UPDATE users SET password_hash=? WHERE user_id=?",
                                   (_hash_password(password, row["salt"]), row["user_id"]))
                self._conn.commit()
            result = {"user_id": row["user_id"], "username": row["username"],
                      "role": row["role"], "status": row["status"],
                      "display_name": row["display_name"], "token": None}
            if row["status"] != "approved":
                return result
            result["token"] = self._issue_token(row["user_id"])
            return result

    def _issue_token(self, user_id: str) -> str:
        token = secrets.token_hex(32)
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS)).isoformat()
        self._conn.execute(
            "INSERT INTO tokens(token, user_id, expires_at) VALUES(?,?,?)",
            (token, user_id, expires_at),
        )
        # Prune old tokens for this user (keep last 10)
        self._conn.execute(
            """DELETE FROM tokens WHERE user_id=? AND token NOT IN (
                SELECT token FROM tokens WHERE user_id=? ORDER BY expires_at DESC LIMIT 10
            )""",
            (user_id, user_id),
        )
        self._conn.commit()
        return token

    def login(self, username: str, password: str) -> Optional[str]:
        """Login and return a session token, or None if invalid / not approved."""
        result = self.authenticate(username, password)
        if result is None:
            return None
        return result["token"]

    def logout(self, token: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM tokens WHERE token=?", (token,))
            self._conn.commit()

    def verify_token(self, token: str) -> Optional[dict]:
        """Return user info if token is valid, else None."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            row = self._conn.execute(
                """SELECT u.user_id, u.username, u.role, u.status, u.display_name
                   FROM tokens t
                   JOIN users u ON t.user_id=u.user_id
                   WHERE t.token=? AND t.expires_at > ?""",
                (token, now),
            ).fetchone()
            if row is None:
                return None
            return dict(row)

    def get_user_by_id(self, user_id: str) -> Optional[dict]:
        with self._lock:
            row = self._conn.execute(
                """SELECT user_id, username, created_at, role, status, display_name
                   FROM users WHERE user_id=?""", (user_id,),
            ).fetchone()
            return dict(row) if row else None

    # --- CLB administration -------------------------------------------------

    def _require_role(self, token: str, allowed: tuple) -> dict:
        user = self.verify_token(token)
        if user is None:
            raise PermissionError("invalid or expired token")
        if user["role"] not in allowed:
            raise PermissionError(f"requires one of roles: {', '.join(allowed)}")
        return user

    def list_users(self, token: str) -> list:
        """Owner/deputy only: member directory with role and approval status."""
        self._require_role(token, ("owner", "deputy"))
        with self._lock:
            rows = self._conn.execute(
                """SELECT user_id, username, role, status, display_name, created_at
                   FROM users ORDER BY created_at""").fetchall()
            return [dict(r) for r in rows]

    def list_directory(self, token: str) -> list:
        """Any approved user: public member directory (no status, no hashes).

        Needed for member-to-member messaging — every member can find and
        message every other member.
        """
        user = self.verify_token(token)
        if user is None:
            raise PermissionError("invalid or expired token")
        with self._lock:
            rows = self._conn.execute(
                """SELECT user_id, username, role, display_name FROM users
                   WHERE status='approved' ORDER BY display_name, username""").fetchall()
            return [dict(r) for r in rows]

    def approve_user(self, token: str, user_id: str) -> None:
        """Owner/deputy approve a pending registration."""
        self._require_role(token, ("owner", "deputy"))
        with self._lock, self._conn:
            cur = self._conn.execute(
                "UPDATE users SET status='approved' WHERE user_id=?", (user_id,))
            if cur.rowcount == 0:
                raise ValueError("user not found")

    def set_role(self, token: str, user_id: str, role: str) -> None:
        """Owner only. Another owner's role cannot be reassigned."""
        if role not in ROLES:
            raise ValueError(f"unknown role: {role}")
        actor = self._require_role(token, ("owner",))
        target = self.get_user_by_id(user_id)
        if target is None:
            raise ValueError("user not found")
        if target["role"] == "owner" and target["user_id"] != actor["user_id"]:
            raise PermissionError("another owner's role cannot be reassigned")
        with self._lock, self._conn:
            self._conn.execute("UPDATE users SET role=? WHERE user_id=?", (role, user_id))

    def change_password(self, token: str, old_password: str, new_password: str) -> None:
        user = self.verify_token(token)
        if user is None:
            raise PermissionError("invalid or expired token")
        if not new_password or len(new_password) < 8:
            raise ValueError("Mật khẩu mới phải có ít nhất 8 ký tự")
        with self._lock:
            row = self._conn.execute(
                "SELECT password_hash, salt FROM users WHERE user_id=?", (user["user_id"],)
            ).fetchone()
            if not row or not _verify_password(old_password, row["salt"], row["password_hash"]):
                raise ValueError("Mật khẩu hiện tại không đúng")
            salt = secrets.token_hex(16)
            pw_hash = _hash_password(new_password, salt)
            with self._conn:
                self._conn.execute(
                    "UPDATE users SET password_hash=?, salt=? WHERE user_id=?",
                    (pw_hash, salt, user["user_id"]),
                )

    def update_profile(self, token: str, display_name: str) -> dict:
        user = self.verify_token(token)
        if user is None:
            raise PermissionError("invalid or expired token")
        display_name = display_name.strip()
        if not display_name:
            raise ValueError("Tên hiển thị không được để trống")
        with self._lock, self._conn:
            self._conn.execute(
                "UPDATE users SET display_name=? WHERE user_id=?",
                (display_name, user["user_id"]),
            )
        user["display_name"] = display_name
        return user

    def create_owner_account(self, username: str, password: str,
                             display_name: str = "") -> dict:
        """Bootstrap the first CLB owner. Refuses if any owner already exists."""
        with self._lock:
            owners = self._conn.execute(
                "SELECT COUNT(*) AS c FROM users WHERE role='owner'").fetchone()["c"]
        if owners > 0:
            raise ValueError("an owner account already exists")
        return self.register(username, password, display_name=display_name or username,
                             status="approved", role="owner")


# Singleton
_auth_db: Optional[AuthDB] = None


def get_auth_db() -> AuthDB:
    global _auth_db
    if _auth_db is None:
        _auth_db = AuthDB()
    return _auth_db
