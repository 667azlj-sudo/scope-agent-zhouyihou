# -*- coding: utf-8 -*-
"""test_chat.py —— 测试聊天 API"""
import httpx
import sqlite3

# 确保测试用户存在
conn = sqlite3.connect("scope_agent.db")
conn.execute("INSERT OR IGNORE INTO users (name, role) VALUES ('张总','manager')")
conn.execute("INSERT OR IGNORE INTO users (name, role) VALUES ('小李','employee')")
conn.commit()
# 查用户的 id
uid_zhang = conn.execute("SELECT id FROM users WHERE name='张总'").fetchone()[0]
uid_li = conn.execute("SELECT id FROM users WHERE name='小李'").fetchone()[0]
conn.close()

base = "http://127.0.0.1:8000"

# 1. 创建群聊（老板 + 员工）
r = httpx.post(f"{base}/api/chats",
               json={"type": "group", "name": "项目组", "member_ids": [uid_zhang, uid_li]})
cid = r.json()["chat_id"]
print(f"1. 创建群聊，chat_id={cid}")

# 2. 老板发消息
r = httpx.post(f"{base}/api/chats/{cid}/messages",
               json={"sender": "张总", "content": "这个项目今天开始，大家加油"})
print(f"2. 老板发言 → {r.json()['msg']}")

# 3. 员工在群聊里回应
r = httpx.post(f"{base}/api/chats/{cid}/messages",
               json={"sender": "小李", "content": "收到，我负责开发模块"})
print(f"3. 员工回应 → {r.json()['msg']}")

# 4. 获取群聊消息
r = httpx.get(f"{base}/api/chats/{cid}/messages")
print(f"4. 群聊消息列表：")
for m in r.json()["messages"]:
    print(f"    {m['content']}")
