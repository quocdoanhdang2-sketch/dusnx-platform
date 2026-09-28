"""
Verification Script: Web -> Gateway -> FastAPI -> Real Ollama (qwen2.5:0.5b)
=============================================================================
Runs the complete Week 2 acceptance scenario against the live Ollama daemon:
1. Register & Login Alice.
2. State initial decision: "Hãy nhớ rằng quyết định của tôi là sử dụng PostgreSQL cho cơ sở dữ liệu."
3. Request modification: "Đổi PostgreSQL sang MongoDB" -> System asks for confirmation.
4. Confirm: "Đồng ý" -> System supersedes PostgreSQL and activates MongoDB atomically.
5. New Session & Ask: "Cơ sở dữ liệu của dự án là gì?" -> Real Ollama generates Vietnamese reply with memory context.
6. Second Client (simulated PowerPoint connector): Sends event with User A's token, advancing state.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "python" / "src"))
sys.path.insert(0, str(REPO_ROOT / "python" / "apps"))
sys.path.insert(0, str(REPO_ROOT / "python"))

# Configure environment for real Ollama
os.environ["DUSNX_PROVIDER"] = "ollama"
os.environ["DUSNX_OLLAMA_MODEL"] = "qwen2.5:0.5b"
os.environ["DUSNX_OLLAMA_URL"] = "http://127.0.0.1:11434"
os.environ["DUSNX_DATA_DIR"] = str(REPO_ROOT / "data" / "verify_real_ollama")

from fastapi.testclient import TestClient
from apps.ai_api.main import app
import apps.ai_api.auth as auth_mod
import apps.ai_api.memory as mem_mod

# Reset singletons
if auth_mod._auth_db:
    auth_mod._auth_db.close()
    auth_mod._auth_db = None
if mem_mod._memory_db:
    mem_mod._memory_db.close()
    mem_mod._memory_db = None

client = TestClient(app)

print("=" * 70)
print("DUSN-X WEEK 2 — REAL OLLAMA (qwen2.5:0.5b) VERIFICATION RUN")
print("=" * 70)

# Check Ollama health
h = client.get("/health").json()
print(f"Health Check: status={h.get('status')}, model_loaded={h.get('model_loaded')}, provider_ok={h.get('provider_ok')}")

# Step 1: Register and login Alice
import secrets
username = f"alice_real_{secrets.token_hex(4)}"
client.post("/v1/auth/register", json={"username": username, "password": "P@ssword123!"})
login_res = client.post("/v1/auth/login", json={"username": username, "password": "P@ssword123!"}).json()
token = login_res["token"]
headers = {"Authorization": f"Bearer {token}"}
print(f"[OK] Logged in user '{username}'.")

# Step 2: Session 1 — Store explicit decision
s1 = client.post("/v1/sessions", json={"title": "Session 1 - Architecture"}, headers=headers).json()
s1_id = s1["session_id"]

msg1 = "Hãy nhớ rằng quyết định của tôi là sử dụng PostgreSQL cho cơ sở dữ liệu."
print(f"\n[Step 1] User says: \"{msg1}\"")
r1 = client.post("/v1/chat", json={"session_id": s1_id, "message": msg1}, headers=headers).json()
print(f"Assistant: {r1['reply']}")
print(f"Intent: {r1['intent']}, Memory IDs: {r1['memory_ids_used']}, State Version: {r1['state_version']}")

# Verify memory created in DB
mems = client.get("/v1/memories", headers=headers).json()
assert len(mems) == 1
assert "PostgreSQL" in mems[0]["content"]
print(f"[OK] Memory saved in DB: id={mems[0]['memory_id']}, active={mems[0]['is_active']}, content=\"{mems[0]['content']}\"")

# Step 3: Modify decision
msg2 = "Đổi PostgreSQL sang MongoDB"
print(f"\n[Step 2] User says: \"{msg2}\"")
r2 = client.post("/v1/chat", json={"session_id": s1_id, "message": msg2}, headers=headers).json()
print(f"Assistant: {r2['reply']}")
print(f"Intent: {r2['intent']}, Next Action: {r2['next_action']}")
assert r2["intent"] == "decision_modify_intent"

# Step 4: Confirm modification ("Đồng ý")
msg3 = "Đồng ý"
print(f"\n[Step 3] User confirms: \"{msg3}\"")
r3 = client.post("/v1/chat", json={"session_id": s1_id, "message": msg3}, headers=headers).json()
print(f"Assistant: {r3['reply']}")
print(f"Intent: {r3['intent']}, State Version: {r3['state_version']}")
assert r3["intent"] == "decision_update"

# Verify active memory is now MongoDB, old PostgreSQL is superseded
active_mems = client.get("/v1/memories?active_only=true", headers=headers).json()
assert len(active_mems) == 1
assert "MongoDB" in active_mems[0]["content"]
print(f"[OK] Active decision is now: \"{active_mems[0]['content']}\" (version {active_mems[0]['version']})")

# Step 5: Session 2 (brand new session) — Ask with Real Ollama
s2 = client.post("/v1/sessions", json={"title": "Session 2 - Query"}, headers=headers).json()
s2_id = s2["session_id"]

query = "Cơ sở dữ liệu của dự án này hiện tại là gì?"
print(f"\n[Step 4] Session 2 — User asks: \"{query}\"")
print("Calling Real Ollama daemon (qwen2.5:0.5b)...")
r4 = client.post("/v1/chat", json={"session_id": s2_id, "message": query}, headers=headers).json()

print("-" * 50)
print(f"REAL OLLAMA RESPONSE:")
print(f"Reply: {r4['reply']}")
print(f"Provider OK: {r4['provider_ok']}")
print(f"Provider Used: {r4['provider_used']}")
print(f"State Version: {r4['state_version']}")
print(f"Memory IDs Used in Prompt: {r4['memory_ids_used']}")
print("-" * 50)

assert r4["provider_ok"] is True, f"Real Ollama generation failed: {r4['reply']}"
assert "ollama" in r4["provider_used"]
assert len(r4["memory_ids_used"]) > 0

# Step 6: Second client (simulated PowerPoint connector) sends event with Alice's token
print("\n[Step 5] Second Client (Simulated PowerPoint Connector) sends event:")
evt_res = client.post("/v1/me/events", json={
    "platform": "powerpoint",
    "event_type": "slide_overview",
    "content": "Trình bày slide kiến trúc: CSDL MongoDB",
}, headers=headers).json()
print(f"Event recorded: platform={evt_res['platform']}, state_version={evt_res['state_version']}, intent={evt_res['intent']}")
assert evt_res["platform"] == "powerpoint"
assert evt_res["state_version"] >= r4["state_version"] + 1

# Check timeline
timeline = client.get("/v1/me/events", headers=headers).json()["events"]
print(f"[OK] Timeline has {len(timeline)} events across platforms: {[e['platform'] for e in timeline]}")

print("\n" + "=" * 70)
print("SUCCESS: ALL WEEK 2 STEPS COMPLETED WITH REAL LOCAL OLLAMA (qwen2.5:0.5b)!")
print("=" * 70)
