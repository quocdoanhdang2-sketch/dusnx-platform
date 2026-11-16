"""Club internal messaging tests."""
from __future__ import annotations

import pytest

from apps.ai_api import auth, club_chat


@pytest.fixture()
def dbs(tmp_path, monkeypatch):
    monkeypatch.setenv("DUSNX_DATA_DIR", str(tmp_path))
    auth._auth_db = None
    club_chat._chat_db = None
    adb = auth.get_auth_db()
    adb.create_owner_account("chu", "password123", "Nguyễn Minh Anh")
    adb.register("vytran", "password123", display_name="Trần Hà Vy", status="approved", role="lead")
    adb.register("long", "password123", display_name="Vũ Hoàng Long", status="approved")
    cdb = club_chat.get_club_chat_db()
    yield adb, cdb
    cdb.close()
    adb.close()
    auth._auth_db = None
    club_chat._chat_db = None


def _ids(adb, *names):
    out = {}
    token = adb.login("chu", "password123")
    for u in adb.list_users(token):
        if u["username"] in names:
            out[u["username"]] = u["user_id"]
    return out


def test_dm_roundtrip_and_isolation(dbs):
    adb, cdb = dbs
    ids = _ids(adb, "vytran", "long")
    conv = cdb.create_dm(ids["vytran"], ids["long"])
    msg = cdb.send(conv, ids["vytran"], "Em gửi anh file poster nhé")
    assert msg["message_id"]
    got = cdb.list_messages(conv, ids["long"])
    assert [m["content"] for m in got] == ["Em gửi anh file poster nhé"]
    # Third member cannot read the DM.
    owner = _ids(adb, "chu")["chu"]
    with pytest.raises(PermissionError):
        cdb.list_messages(conv, owner)


def test_dm_is_reused_not_duplicated(dbs):
    adb, cdb = dbs
    ids = _ids(adb, "vytran", "long")
    assert cdb.create_dm(ids["vytran"], ids["long"]) == cdb.create_dm(ids["long"], ids["vytran"])


def test_group_and_pin_permissions(dbs):
    adb, cdb = dbs
    ids = _ids(adb, "chu", "vytran", "long")
    conv = cdb.create_group(ids["vytran"], "Ban truyền thông", "truyen-thong",
                            [ids["long"]], creator_can_pin=True)
    cdb.send(conv, ids["vytran"], "Deadline poster 4/12 nhé cả nhà")
    cdb.send(conv, ids["long"], "Em nhận task ạ")
    msgs = cdb.list_messages(conv, ids["long"])
    assert len(msgs) == 2
    # Member without can_pin cannot pin.
    with pytest.raises(PermissionError):
        cdb.pin_message(conv, ids["long"], msgs[0]["message_id"])
    cdb.pin_message(conv, ids["vytran"], msgs[0]["message_id"])
    pinned = [m for m in cdb.list_messages(conv, ids["long"]) if m["pinned"]]
    assert len(pinned) == 1
    # Non-member cannot send.
    with pytest.raises(PermissionError):
        cdb.send(conv, ids["chu"], "xin vào nhóm với")


def test_list_conversations_per_user(dbs):
    adb, cdb = dbs
    ids = _ids(adb, "chu", "vytran", "long")
    dm = cdb.create_dm(ids["vytran"], ids["long"])
    grp = cdb.create_group(ids["vytran"], "Ban truyền thông", "truyen-thong", [ids["long"]])
    vy_convs = {c["conv_id"] for c in cdb.list_conversations(ids["vytran"])}
    an_convs = {c["conv_id"] for c in cdb.list_conversations(ids["long"])}
    chu_convs = {c["conv_id"] for c in cdb.list_conversations(ids["chu"])}
    assert {dm, grp} <= vy_convs and {dm, grp} <= an_convs
    assert chu_convs == set()


def test_directory_lists_approved_members_only(dbs):
    adb, _ = dbs
    adb.register("pending1", "password123", status="pending")
    token = adb.login("long", "password123")
    directory = adb.list_directory(token)
    names = {u["username"] for u in directory}
    assert "pending1" not in names
    assert {"chu", "vytran", "long"} <= names
    vy = next(u for u in directory if u["username"] == "vytran")
    assert vy["role"] == "lead" and vy["display_name"] == "Trần Hà Vy"
