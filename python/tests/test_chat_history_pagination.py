"""History must include recent messages and paginate without cross-user cursors."""
from test_week2_acceptance import _register_and_login
from test_week2_acceptance import client as client  # noqa: PLC0414 -- pytest fixture re-export
from test_week2_acceptance import isolated_week2_env as isolated_week2_env  # noqa: PLC0414

from apps.ai_api.memory import get_memory_db


def test_recent_pages_are_stable_when_messages_are_appended(client, monkeypatch):
    _, token = _register_and_login(client, "history_owner")
    headers = {"Authorization": f"Bearer {token}"}
    uid = client.get("/v1/auth/me", headers=headers).json()["user_id"]
    sid = client.post("/v1/sessions", headers=headers, json={}).json()["session_id"]
    db = get_memory_db()
    monkeypatch.setattr("apps.ai_api.memory._now", lambda: "2026-11-02T00:00:00+00:00")
    for i in range(205):
        db.append_message(sid, uid, "user", f"turn-{i}")
    url = f"/v1/sessions/{sid}/messages/page"
    first = client.get(url, headers=headers).json()
    assert [m["content"] for m in first["messages"]] == [f"turn-{i}" for i in range(105, 205)]
    db.append_message(sid, uid, "assistant", "newly-appended")
    second = client.get(url, headers=headers, params={"before": first["next_before"]}).json()
    third = client.get(url, headers=headers, params={"before": second["next_before"]}).json()
    assert [m["content"] for m in third["messages"] + second["messages"] + first["messages"]] == [
        f"turn-{i}" for i in range(205)
    ]
    assert third["next_before"] is None
    # The original oldest-first list endpoint remains available to existing clients.
    assert client.get(f"/v1/sessions/{sid}/messages", headers=headers).json()[0]["content"] == "turn-0"
    for limit in (-1, 0, 101):
        assert client.get(url, headers=headers, params={"limit": limit}).status_code == 422
        assert client.get(f"/v1/sessions/{sid}/messages", headers=headers,
                          params={"limit": limit}).status_code == 422
    assert client.get(f"/v1/sessions/{sid}/messages", headers=headers,
                      params={"offset": -1}).status_code == 422
    assert client.get(url, headers=headers, params={"before": "missing"}).status_code == 400
    db._conn.execute("UPDATE chat_messages SET memory_ids_used=? WHERE message_id=?",
                     ("[broken", first["messages"][-1]["message_id"]))
    db._conn.commit()
    repaired_page = client.get(url, headers=headers)
    assert repaired_page.status_code == 200
    target = next(m for m in repaired_page.json()["messages"] if m["content"] == "turn-204")
    assert target["memory_ids_used"] == []


def test_history_cursor_and_session_are_scoped_to_owner(client):
    db = get_memory_db()
    def owner(name):
        _, token = _register_and_login(client, name)
        headers = {"Authorization": f"Bearer {token}"}
        uid = client.get("/v1/auth/me", headers=headers).json()["user_id"]
        sid = client.post("/v1/sessions", headers=headers, json={}).json()["session_id"]
        message = db.append_message(sid, uid, "user", "private")
        return headers, uid, sid, message["message_id"]
    a, _, sid, cursor = owner("history_alice")
    b, _, other, _ = owner("history_bob")
    url = f"/v1/sessions/{sid}/messages/page"
    assert client.get(url, headers=b).status_code == 404
    assert client.get(f"/v1/sessions/{other}/messages/page", headers=b,
                      params={"before": cursor}).status_code == 400
    own_other = client.post("/v1/sessions", headers=a, json={}).json()["session_id"]
    assert client.get(f"/v1/sessions/{own_other}/messages/page", headers=a,
                      params={"before": cursor}).status_code == 400
    assert client.get(f"/v1/sessions/{own_other}/messages/page", headers=a).json() == {
        "messages": [], "next_before": None,
    }
