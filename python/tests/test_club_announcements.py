import pytest
from apps.ai_api.club_chat import ClubChatDB


def test_club_chat_delete_message(tmp_path, monkeypatch):
    monkeypatch.setenv("DUSNX_DATA_DIR", str(tmp_path))
    db = ClubChatDB()
    # Seed messages
    db.ensure_default_channels("admin")
    convs = db.list_conversations("admin")
    toan_clb = next(c for c in convs if c.get("unit") == "toan-clb")
    
    msg = db.send(toan_clb["conv_id"], "admin", "Test announcement to delete")
    assert msg["message_id"]
    
    # Verify it exists
    msgs = db.list_messages(toan_clb["conv_id"], "admin")
    assert any(m["message_id"] == msg["message_id"] for m in msgs)
    
    # Delete it
    deleted = db.delete_message(msg["message_id"])
    assert deleted is True
    
    # Verify it no longer exists
    msgs_after = db.list_messages(toan_clb["conv_id"], "admin")
    assert not any(m["message_id"] == msg["message_id"] for m in msgs_after)
    
    # Deleting non-existent returns False
    assert db.delete_message("non_existent_id") is False
    db.close()
