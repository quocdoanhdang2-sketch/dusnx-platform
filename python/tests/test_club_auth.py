"""CLB role + approval flow tests (auth module)."""
from __future__ import annotations

import importlib

import pytest

from apps.ai_api import auth


@pytest.fixture()
def authdb(tmp_path, monkeypatch):
    monkeypatch.setenv("DUSNX_DATA_DIR", str(tmp_path))
    # Club runtime default: new registrations start as pending
    monkeypatch.setenv("DUSNX_DEFAULT_USER_STATUS", "pending")
    auth._auth_db = None
    db = auth.get_auth_db()
    yield db
    db.close()
    auth._auth_db = None


def test_register_defaults_to_pending_and_cannot_login(authdb):
    authdb.register("anh", "password123", display_name="Nguyễn Minh Anh")
    assert authdb.login("an", "password123") is None
    result = authdb.authenticate("anh", "password123")
    assert result["status"] == "pending"
    assert result["token"] is None
    assert result["role"] == "member"


def test_approve_then_login_issues_token(authdb):
    authdb.register("bao", "password123")
    owner = authdb.create_owner_account("chu", "password123", "Nguyễn Minh Anh")
    token = authdb.login("chu", "password123")
    user = authdb.get_user_by_id(owner["user_id"])
    assert user["role"] == "owner" and user["status"] == "approved"
    authdb.approve_user(token, authdb.authenticate("bao", "password123")["user_id"])
    assert authdb.login("bao", "password123") is not None


def test_second_owner_account_is_refused(authdb):
    authdb.create_owner_account("chu1", "password123")
    with pytest.raises(ValueError, match="already exists"):
        authdb.create_owner_account("chu2", "password123")


def test_role_gating_for_admin_ops(authdb):
    owner_token = authdb.login("chu", "password123") if False else None
    authdb.create_owner_account("chu", "password123")
    owner_token = authdb.login("chu", "password123")
    authdb.register("mem", "password123", status="approved")
    mem_token = authdb.login("mem", "password123")

    users = authdb.list_users(owner_token)
    assert {u["role"] for u in users} == {"owner", "member"}
    with pytest.raises(PermissionError):
        authdb.list_users(mem_token)

    mem_id = authdb.authenticate("mem", "password123")["user_id"]
    with pytest.raises(PermissionError):
        authdb.set_role(mem_token, mem_id, "deputy")
    authdb.set_role(owner_token, mem_id, "deputy")
    assert authdb.get_user_by_id(mem_id)["role"] == "deputy"

    with pytest.raises(ValueError, match="unknown role"):
        authdb.set_role(owner_token, mem_id, "president")


def test_owner_role_cannot_be_reassigned_by_another_owner(authdb):
    authdb.create_owner_account("chu", "password123")
    token = authdb.login("chu", "password123")
    owner_id = authdb.authenticate("chu", "password123")["user_id"]
    authdb.register("deputy1", "password123", status="approved", role="deputy")
    deputy_id = authdb.authenticate("deputy1", "password123")["user_id"]
    with pytest.raises(PermissionError):
        # Only one owner exists; simulate another owner via direct promotion
        # path: deputy tries to demote the owner.
        authdb.set_role(authdb.login("deputy1", "password123"), owner_id, "member")
    # Owner keeps their role regardless.
    assert authdb.get_user_by_id(owner_id)["role"] == "owner"


def test_verify_token_returns_role(authdb):
    authdb.create_owner_account("chu", "password123", "Nguyễn Minh Anh")
    token = authdb.login("chu", "password123")
    info = authdb.verify_token(token)
    assert info["role"] == "owner"
    assert info["display_name"] == "Nguyễn Minh Anh"


def test_legacy_users_stay_approved_after_migration(tmp_path, monkeypatch):
    """An auth.db created before roles existed keeps working after upgrade."""
    import sqlite3

    monkeypatch.setenv("DUSNX_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "auth.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE users (
            user_id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE tokens (token TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                             expires_at TEXT NOT NULL);
    """)
    conn.execute(
        "INSERT INTO users VALUES('u1','olduser','deadbeef'*8, 'salt1234', '2026-01-01')")
    conn.commit()
    conn.close()

    auth._auth_db = None
    db = auth.get_auth_db()
    try:
        user = db.get_user_by_id("u1")
        assert user["role"] == "member"
        assert user["status"] == "approved"
    finally:
        db.close()
        auth._auth_db = None
