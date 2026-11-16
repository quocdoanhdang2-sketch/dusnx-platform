"""
CLB IT HTTP endpoint tests
==========================
Covers the club flows over FastAPI TestClient:
- Register returns pending (DUSNX_DEFAULT_USER_STATUS=pending), login 403 until approved
- Owner/deputy approve + role assignment endpoints with permission gating
- /v1/auth/me returns role + display_name
- Directory endpoint for all approved users
- Internal messaging: DM, group, send/list, pin permissions
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import apps.ai_api.auth as auth_mod
import apps.ai_api.club_chat as chat_mod
from apps.ai_api.main import app


@pytest.fixture(autouse=True)
def isolated_club_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DUSNX_DATA_DIR", str(tmp_path))
    # Club runtime default: new registrations need manager approval
    monkeypatch.setenv("DUSNX_DEFAULT_USER_STATUS", "pending")
    if auth_mod._auth_db is not None:
        auth_mod._auth_db.close()
        auth_mod._auth_db = None
    if getattr(chat_mod, "_chat_db", None) is not None:
        chat_mod._chat_db.close()
        chat_mod._chat_db = None
    yield
    if auth_mod._auth_db is not None:
        auth_mod._auth_db.close()
        auth_mod._auth_db = None
    if getattr(chat_mod, "_chat_db", None) is not None:
        chat_mod._chat_db.close()
        chat_mod._chat_db = None


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_owner(client: TestClient) -> tuple[str, str]:
    """Ensure the club owner account exists (idempotent) and log in."""
    db = auth_mod.get_auth_db()
    try:
        db.create_owner_account("clubowner", "ownerpass123", "Nguyễn Minh Anh")
    except ValueError:
        pass  # owner already created by an earlier caller in this test
    res = client.post("/v1/auth/login", json={"username": "clubowner", "password": "ownerpass123"})
    assert res.status_code == 200, res.text
    return res.json().get("user_id", "me"), res.json()["token"]


def _register(client: TestClient, username: str, display: str = "") -> dict:
    r = client.post("/v1/auth/register", json={
        "username": username, "password": "password123", "display_name": display,
    })
    assert r.status_code == 201, r.text
    return r.json()


class TestClubAuthFlow:
    def test_register_pending_then_approve_then_login(self, client):
        reg = _register(client, "thanhvien1", "Vũ Hoàng Long")
        assert reg["status"] == "pending"

        # Cannot login while pending
        r = client.post("/v1/auth/login", json={"username": "thanhvien1", "password": "password123"})
        assert r.status_code == 403

        _, owner_token = _make_owner(client)
        ap = client.post(f"/v1/club/members/{reg['user_id']}/approve", headers=_headers(owner_token))
        assert ap.status_code == 200, ap.text

        r = client.post("/v1/auth/login", json={"username": "thanhvien1", "password": "password123"})
        assert r.status_code == 200
        body = r.json()
        assert body["role"] == "member"
        assert body["display_name"] == "Vũ Hoàng Long"

        me = client.get("/v1/auth/me", headers=_headers(body["token"])).json()
        assert me["role"] == "member"
        assert me["display_name"] == "Vũ Hoàng Long"
        assert me["status"] == "approved"

    def test_login_wrong_password_still_401(self, client):
        _register(client, "wrongpw1", "X")
        r = client.post("/v1/auth/login", json={"username": "wrongpw1", "password": "badbadbad"})
        assert r.status_code == 401

    def test_member_cannot_list_members_or_set_role(self, client):
        _, owner_token = _make_owner(client)
        reg = _register(client, "plainmember", "Thành viên")
        client.post(f"/v1/club/members/{reg['user_id']}/approve", headers=_headers(owner_token))
        login = client.post("/v1/auth/login", json={"username": "plainmember", "password": "password123"}).json()
        token = login["token"]

        assert client.get("/v1/club/members", headers=_headers(token)).status_code == 403
        r = client.post(f"/v1/club/members/{reg['user_id']}/role", json={"role": "lead"}, headers=_headers(token))
        assert r.status_code == 403

    def test_owner_assigns_lead_role_and_directory(self, client):
        _, owner_token = _make_owner(client)
        reg = _register(client, "futurelead", "Trưởng ban")
        client.post(f"/v1/club/members/{reg['user_id']}/approve", headers=_headers(owner_token))
        r = client.post(f"/v1/club/members/{reg['user_id']}/role", json={"role": "lead"}, headers=_headers(owner_token))
        assert r.status_code == 200

        # Owner sees full member list; any approved user sees directory
        members = client.get("/v1/club/members", headers=_headers(owner_token)).json()["members"]
        roles = {m["user_id"]: m["role"] for m in members}
        assert roles[reg["user_id"]] == "lead"

        directory = client.get("/v1/club/directory", headers=_headers(owner_token)).json()["members"]
        assert any(m["user_id"] == reg["user_id"] for m in directory)
        # Pending users are excluded from directory
        pending_reg = _register(client, "waitinguser", "Chờ duyệt")
        directory = client.get("/v1/club/directory", headers=_headers(owner_token)).json()["members"]
        assert all(m["user_id"] != pending_reg["user_id"] for m in directory)

    def test_unknown_role_rejected(self, client):
        _, owner_token = _make_owner(client)
        reg = _register(client, "roletest1", "R")
        client.post(f"/v1/club/members/{reg['user_id']}/approve", headers=_headers(owner_token))
        r = client.post(f"/v1/club/members/{reg['user_id']}/role", json={"role": "superadmin"}, headers=_headers(owner_token))
        assert r.status_code == 400


class TestClubMessagingHttp:
    def _setup_two_members(self, client):
        _, owner_token = _make_owner(client)
        users = {}
        for uname, display in (("msgusera", "Ngưởi A"), ("msguserb", "NgườI B")):
            reg = _register(client, uname, display)
            client.post(f"/v1/club/members/{reg['user_id']}/approve", headers=_headers(owner_token))
            login = client.post("/v1/auth/login", json={"username": uname, "password": "password123"}).json()
            users[uname] = (reg["user_id"], login["token"])
        return users

    def test_dm_send_list_and_isolation(self, client):
        users = self._setup_two_members(client)
        (uid_a, token_a) = users["msgusera"]
        (uid_b, token_b) = users["msguserb"]

        r = client.post("/v1/club/dm", json={"user_id": uid_b}, headers=_headers(token_a))
        assert r.status_code == 201, r.text
        conv = r.json()
        assert conv["kind"] == "dm"

        # DM is reused when created from the other side
        r2 = client.post("/v1/club/dm", json={"user_id": uid_a}, headers=_headers(token_b))
        assert r2.json()["conv_id"] == conv["conv_id"]

        msg = client.post(
            f"/v1/club/conversations/{conv['conv_id']}/messages",
            json={"content": "Chào bạn, chiều nay họp ban nhé"},
            headers=_headers(token_a),
        )
        assert msg.status_code == 201, msg.text

        msgs = client.get(f"/v1/club/conversations/{conv['conv_id']}/messages", headers=_headers(token_b)).json()
        assert any("họp ban" in m["content"] for m in msgs["messages"])

        # Empty message rejected
        bad = client.post(
            f"/v1/club/conversations/{conv['conv_id']}/messages",
            json={"content": "   "}, headers=_headers(token_a),
        )
        assert bad.status_code == 400

    def test_group_pin_permissions(self, client):
        users = self._setup_two_members(client)
        (uid_a, token_a) = users["msgusera"]
        (uid_b, token_b) = users["msguserb"]

        g = client.post("/v1/club/groups", json={
            "name": "Ban Kỹ thuật", "unit": "ky-thuat", "member_ids": [uid_b],
        }, headers=_headers(token_a))
        assert g.status_code == 201, g.text
        conv_id = g.json()["conv_id"]

        m1 = client.post(f"/v1/club/conversations/{conv_id}/messages", json={"content": "Thông báo quan trọng"}, headers=_headers(token_a)).json()
        pin = client.post(f"/v1/club/conversations/{conv_id}/pin", json={"message_id": m1["message_id"], "pinned": True}, headers=_headers(token_a))
        assert pin.status_code == 200

        # Member without can_pin cannot pin
        m2 = client.post(f"/v1/club/conversations/{conv_id}/messages", json={"content": "Tin thường"}, headers=_headers(token_b)).json()
        denied = client.post(f"/v1/club/conversations/{conv_id}/pin", json={"message_id": m2["message_id"]}, headers=_headers(token_b))
        assert denied.status_code == 403

        # Conversation list per user contains the group
        convs = client.get("/v1/club/conversations", headers=_headers(token_b)).json()["conversations"]
        assert any(c["conv_id"] == conv_id for c in convs)

    def test_non_member_cannot_send_or_read(self, client):
        users = self._setup_two_members(client)
        (uid_a, token_a) = users["msgusera"]
        (uid_b, token_b) = users["msguserb"]

        conv = client.post("/v1/club/dm", json={"user_id": uid_b}, headers=_headers(token_a)).json()

        # Owner is not part of this DM
        _, owner_token = _make_owner(client)
        r = client.post(f"/v1/club/conversations/{conv['conv_id']}/messages", json={"content": "x"}, headers=_headers(owner_token))
        assert r.status_code == 403
        r = client.get(f"/v1/club/conversations/{conv['conv_id']}/messages", headers=_headers(owner_token))
        assert r.status_code == 403


class TestClubProfile:
    def test_update_profile_and_password(self, client):
        _, owner_token = _make_owner(client)
        reg = _register(client, "proftest", "Ban đầu")
        client.post(f"/v1/club/members/{reg['user_id']}/approve", headers=_headers(owner_token))
        login = client.post("/v1/auth/login", json={"username": "proftest", "password": "password123"}).json()
        token = login["token"]

        # Update display name
        up = client.post("/v1/auth/profile", json={"display_name": "Tên mới"}, headers=_headers(token))
        assert up.status_code == 200, up.text
        assert up.json()["display_name"] == "Tên mới"

        me = client.get("/v1/auth/me", headers=_headers(token)).json()
        assert me["display_name"] == "Tên mới"

        # Change password
        cp = client.post("/v1/auth/password", json={
            "old_password": "password123", "new_password": "newpassword456"
        }, headers=_headers(token))
        assert cp.status_code == 200, cp.text

        # Old password fails, new password succeeds
        fail = client.post("/v1/auth/login", json={"username": "proftest", "password": "password123"})
        assert fail.status_code == 401
        ok = client.post("/v1/auth/login", json={"username": "proftest", "password": "newpassword456"})
        assert ok.status_code == 200


class TestClubDocumentsAndStats:
    def test_list_and_read_documents_and_announcements(self, client):
        _, owner_token = _make_owner(client)
        reg = _register(client, "docviewer", "Xem tài liệu")
        client.post(f"/v1/club/members/{reg['user_id']}/approve", headers=_headers(owner_token))
        token = client.post("/v1/auth/login", json={"username": "docviewer", "password": "password123"}).json()["token"]

        # List documents
        r = client.get("/v1/club/documents", headers=_headers(token))
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["corpus_id"] == "club-it-v1"
        assert len(data["documents"]) >= 10
        assert data["verified"] is True

        # Read specific doc
        first_doc = data["documents"][0]["path"]
        doc_res = client.get(f"/v1/club/documents/{first_doc}", headers=_headers(token))
        assert doc_res.status_code == 200, doc_res.text
        assert len(doc_res.json()["content"]) > 50

        # Verify documents
        v = client.post("/v1/club/documents/verify", headers=_headers(token))
        assert v.status_code == 200
        assert v.json()["verified"] is True

        # Announcements
        ann = client.get("/v1/club/announcements", headers=_headers(token))
        assert ann.status_code == 200
        assert len(ann.json()["announcements"]) >= 1

    def test_stats_permissions(self, client):
        _, owner_token = _make_owner(client)
        reg = _register(client, "normaluser", "Member")
        client.post(f"/v1/club/members/{reg['user_id']}/approve", headers=_headers(owner_token))
        member_token = client.post("/v1/auth/login", json={"username": "normaluser", "password": "password123"}).json()["token"]

        # Member cannot access stats
        assert client.get("/v1/club/stats", headers=_headers(member_token)).status_code == 403

        # Owner can access stats
        stats = client.get("/v1/club/stats", headers=_headers(owner_token))
        assert stats.status_code == 200
        body = stats.json()
        assert "members" in body
        assert "documents" in body
        assert body["members"]["total"] >= 2

