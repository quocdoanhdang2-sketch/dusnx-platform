import urllib.request
import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

base_url = 'http://127.0.0.1:8080'

# 1. Register & Login
uname = 'eval_user_2026'
pword = 'SecurePass123!'
try:
    req = urllib.request.Request(
        f'{base_url}/v1/auth/register',
        data=json.dumps({'username': uname, 'password': pword}).encode(),
        headers={'Content-Type': 'application/json'}
    )
    urllib.request.urlopen(req)
except Exception:
    pass

req = urllib.request.Request(
    f'{base_url}/v1/auth/login',
    data=json.dumps({'username': uname, 'password': pword}).encode(),
    headers={'Content-Type': 'application/json'}
)
with urllib.request.urlopen(req) as r:
    auth_data = json.loads(r.read().decode())
token = auth_data['token']

headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'}

# Get user info
req = urllib.request.Request(f'{base_url}/v1/auth/me', headers=headers)
with urllib.request.urlopen(req) as r:
    me_data = json.loads(r.read().decode())
user_id = me_data['user_id']
print(f'[1] Đăng nhập thành công user={uname}, user_id={user_id}')

# Tạo Phiên 1
req = urllib.request.Request(
    f'{base_url}/v1/sessions',
    data=json.dumps({'title': 'Phiên 1 - Quyết định đám mây'}).encode(),
    headers=headers
)
with urllib.request.urlopen(req) as r:
    s1 = json.loads(r.read().decode())
session_1_id = s1['session_id']
print(f'[2] Tạo Phiên 1: session_id={session_1_id}')

# 2. Lưu quyết định trong Phiên 1
chat_payload = {
    'session_id': session_1_id,
    'message': 'Ghi nhớ quyết định: Chúng tôi chọn GCP cho dự án hạ tầng đám mây năm 2026.',
    'platform': 'web'
}
req = urllib.request.Request(f'{base_url}/v1/chat', data=json.dumps(chat_payload).encode(), headers=headers)
with urllib.request.urlopen(req) as r:
    c1 = json.loads(r.read().decode())
print(f'[3] Lưu quyết định:')
print(f'    Agent={c1.get("agent")}, Intent={c1.get("intent")}, Action={c1.get("next_action")}')
print(f'    Routing Source: {c1.get("routing_source")}')
print(f'    Phản hồi hệ thống: {c1.get("reply")}')

# 3. Yêu cầu sửa quyết định trong Phiên 1 (kích hoạt xác nhận)
chat_payload = {
    'session_id': session_1_id,
    'message': 'Đổi quyết định hạ tầng đám mây sang AWS nhé.',
    'platform': 'web'
}
req = urllib.request.Request(f'{base_url}/v1/chat', data=json.dumps(chat_payload).encode(), headers=headers)
with urllib.request.urlopen(req) as r:
    c2 = json.loads(r.read().decode())
print(f'[4] Yêu cầu đổi quyết định:')
print(f'    Intent={c2.get("intent")}, Action={c2.get("next_action")}')
print(f'    Routing Source: {c2.get("routing_source")}')
print(f'    Hộp thoại xác nhận:\n{c2.get("reply")}')

# 4. Xác nhận thay đổi
chat_payload = {
    'session_id': session_1_id,
    'message': 'Có, tôi xác nhận đổi.',
    'platform': 'web'
}
req = urllib.request.Request(f'{base_url}/v1/chat', data=json.dumps(chat_payload).encode(), headers=headers)
with urllib.request.urlopen(req) as r:
    c3 = json.loads(r.read().decode())
print(f'[5] Đã xác nhận đổi:')
print(f'    Intent={c3.get("intent")}, Action={c3.get("next_action")}')
print(f'    Routing Source: {c3.get("routing_source")}')
print(f'    Phản hồi: {c3.get("reply")}')

# Kiểm tra trí nhớ trong database
req = urllib.request.Request(f'{base_url}/v1/memories?include_inactive=true', headers=headers)
with urllib.request.urlopen(req) as r:
    mems = json.loads(r.read().decode())
print(f'[6] Danh sách trí nhớ (tổng {len(mems)}):')
for m in mems:
    print(f'    - [{m.get("memory_type")}] {m.get("content")} (status={m.get("status")})')

# 5. Mở Phiên mới (Phiên 2)
req = urllib.request.Request(
    f'{base_url}/v1/sessions',
    data=json.dumps({'title': 'Phiên 2 - Truy hồi ngữ cảnh'}).encode(),
    headers=headers
)
with urllib.request.urlopen(req) as r:
    s2 = json.loads(r.read().decode())
session_2_id = s2['session_id']
print(f'[7] Mở Phiên 2 mới: session_id={session_2_id}')

# 6. Hỏi lại trong Phiên 2
chat_payload = {
    'session_id': session_2_id,
    'message': 'Nhắc lại quyết định hạ tầng đám mây năm 2026 của tôi là gì?',
    'platform': 'web'
}
req = urllib.request.Request(f'{base_url}/v1/chat', data=json.dumps(chat_payload).encode(), headers=headers)
with urllib.request.urlopen(req) as r:
    c4 = json.loads(r.read().decode())
print(f'[8] Truy vấn ngữ cảnh trong Phiên 2:')
print(f'    Intent: {c4.get("intent")}')
print(f'    Router Action: {c4.get("next_action")}')
print(f'    Routing Source: {c4.get("routing_source")}')
print(f'    Memories Used: {c4.get("memory_ids_used")}')
print(f'    Câu trả lời: {c4.get("reply")}')
