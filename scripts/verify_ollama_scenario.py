import urllib.request
import json
import sys
import time
import sqlite3
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

base_url = "http://127.0.0.1:8080"
timestamp = int(time.time())
username = f"user_real_{timestamp}"
password = "StrongPassword2026!"

print(f"=== KỊCH BẢN THỰC TẾ DUSN-X VỚI OLLAMA (GATEWAY PORT 8080) ===")
print(f"Khởi tạo tài khoản thử mới: {username}")

# 1. Đăng ký & Đăng nhập
req = urllib.request.Request(
    f"{base_url}/v1/auth/register",
    data=json.dumps({"username": username, "password": password}).encode(),
    headers={"Content-Type": "application/json"}
)
with urllib.request.urlopen(req) as r:
    reg_data = json.loads(r.read().decode())
print(f"[Bước 1] Đăng ký thành công: user_id={reg_data['user_id']}")

req = urllib.request.Request(
    f"{base_url}/v1/auth/login",
    data=json.dumps({"username": username, "password": password}).encode(),
    headers={"Content-Type": "application/json"}
)
with urllib.request.urlopen(req) as r:
    login_data = json.loads(r.read().decode())
token = login_data["token"]
user_id = reg_data["user_id"]
print(f"[Bước 1] Đăng nhập thành công, nhận token Bearer")

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}

# 2. Tạo Phiên 1
req = urllib.request.Request(
    f"{base_url}/v1/sessions",
    data=json.dumps({"title": "Phiên 1 - Chốt quyết định đám mây"}).encode(),
    headers=headers
)
with urllib.request.urlopen(req) as r:
    sess1 = json.loads(r.read().decode())
session_1_id = sess1["session_id"]
print(f"[Bước 2] Đã tạo Phiên 1: session_id={session_1_id}")

# 3. Lưu quyết định dùng GCP
chat_msg_1 = "Ghi nhớ quyết định: Chúng tôi chọn GCP cho dự án hạ tầng đám mây năm 2026."
req = urllib.request.Request(
    f"{base_url}/v1/chat",
    data=json.dumps({"session_id": session_1_id, "message": chat_msg_1, "platform": "web"}).encode(),
    headers=headers
)
with urllib.request.urlopen(req) as r:
    resp1 = json.loads(r.read().decode())
print(f"[Bước 3] Lưu quyết định GCP:")
print(f"  - Intent: {resp1.get('intent')}, Action: {resp1.get('next_action')}, Agent: {resp1.get('agent') or resp1.get('selected_agent')}")
print(f"  - Routing source: {resp1.get('routing_source')}")
print(f"  - Phản hồi: {resp1.get('reply')}")

# 4. Yêu cầu đổi sang AWS
chat_msg_2 = "Đổi quyết định hạ tầng đám mây sang AWS nhé."
req = urllib.request.Request(
    f"{base_url}/v1/chat",
    data=json.dumps({"session_id": session_1_id, "message": chat_msg_2, "platform": "web"}).encode(),
    headers=headers
)
with urllib.request.urlopen(req) as r:
    resp2 = json.loads(r.read().decode())
print(f"[Bước 4] Yêu cầu đổi sang AWS:")
print(f"  - Intent: {resp2.get('intent')}, Action: {resp2.get('next_action')}")
print(f"  - Routing source: {resp2.get('routing_source')}")
print(f"  - Hộp thoại xác nhận:\n{resp2.get('reply')}")

# 5. Xác nhận đổi sang AWS
chat_msg_3 = "Có, tôi xác nhận đổi."
req = urllib.request.Request(
    f"{base_url}/v1/chat",
    data=json.dumps({"session_id": session_1_id, "message": chat_msg_3, "platform": "web"}).encode(),
    headers=headers
)
with urllib.request.urlopen(req) as r:
    resp3 = json.loads(r.read().decode())
print(f"[Bước 5] Xác nhận đổi:")
print(f"  - Intent: {resp3.get('intent')}, Action: {resp3.get('next_action')}")
print(f"  - Routing source: {resp3.get('routing_source')}")
print(f"  - Phản hồi:\n{resp3.get('reply')}")

db_path = Path("python/data/memory.db") if Path("python/data/memory.db").exists() else Path("data/memory.db")
print(f"[Bước 6] Kiểm tra cơ sở dữ liệu SQLite: {db_path}")
if db_path.exists():
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute(
        "SELECT memory_id, content, info_type, is_active, version, superseded_by FROM memories WHERE user_id = ? ORDER BY version ASC",
        (user_id,)
    )
    rows = cursor.fetchall()
    print(f"  Tìm thấy {len(rows)} bản ghi trí nhớ của user {user_id}:")
    for row in rows:
        m_id, content, itype, is_act, ver, sup = row
        status_str = "active" if is_act == 1 else ("superseded" if sup else "inactive")
        print(f"    - ID={m_id[:8]}... | Ver={ver} | Type={itype} | is_active={is_act} ({status_str}) | SupersededBy={sup[:8] if sup else 'None'} | Content=\"{content}\"")
    conn.close()

# 7. Mở Phiên mới (Phiên 2)
req = urllib.request.Request(
    f"{base_url}/v1/sessions",
    data=json.dumps({"title": "Phiên 2 - Hỏi lại quyết định hiện hành"}).encode(),
    headers=headers
)
with urllib.request.urlopen(req) as r:
    sess2 = json.loads(r.read().decode())
session_2_id = sess2["session_id"]
print(f"[Bước 7] Đã tạo Phiên 2 mới: session_id={session_2_id}")

# 8. Hỏi lại quyết định hiện hành
chat_msg_4 = "Quyết định hạ tầng đám mây năm 2026 hiện hành của tôi là gì?"
req = urllib.request.Request(
    f"{base_url}/v1/chat",
    data=json.dumps({"session_id": session_2_id, "message": chat_msg_4, "platform": "web"}).encode(),
    headers=headers
)
with urllib.request.urlopen(req) as r:
    resp4 = json.loads(r.read().decode())

print(f"[Bước 8] KẾT QUẢ TRUY VẤN Ở PHIÊN 2:")
print(f"  - Nguyên văn câu trả lời (reply):\n\"{resp4.get('reply')}\"")
print(f"  - provider_used: {resp4.get('provider_used')}")
print(f"  - model_used: {resp4.get('model_used')}")
print(f"  - memory_ids_used: {resp4.get('memory_ids_used')}")
print(f"  - provider_ok: {resp4.get('provider_ok')}")
print(f"  - routing_source: {resp4.get('routing_source')}")
print(f"  - intent: {resp4.get('intent')}")
print(f"  - next_action: {resp4.get('next_action')}")

reply_lower = resp4.get('reply', '').lower()
aws_present = 'aws' in reply_lower
gcp_as_current = 'chọn gcp' in reply_lower or 'dùng gcp' in reply_lower

print(f"\n[Xác nhận tính đúng đắn]:")
print(f"  - AWS là quyết định hiện hành: {aws_present}")
print(f"  - GCP KHÔNG bị trình bày như quyết định hiện hành: {not gcp_as_current}")
