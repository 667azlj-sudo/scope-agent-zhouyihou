# -*- coding: utf-8 -*-
"""test_api.py —— 测试 Web API 的完整权限审批流"""
import httpx
import sqlite3

# 确保测试用户存在（INSERT OR IGNORE 防重复）
conn = sqlite3.connect("scope_agent.db")
conn.execute("INSERT OR IGNORE INTO users (name, role) VALUES ('张总','manager')")
conn.execute("INSERT OR IGNORE INTO users (name, role) VALUES ('小李','employee')")
conn.commit()
conn.close()

base = "http://127.0.0.1:8000"

# 查待确认事项
r = httpx.get(f"{base}/api/projects/1/tasks")
tasks = r.json()["tasks"]
pending = [t for t in tasks if t["status"] == "pending_review"]
tid = pending[0]["id"]
print(f"待确认 {len(pending)} 个，取 id={tid} 测试\n")

# 1. 员工确认（应拒绝）
r = httpx.post(f"{base}/api/tasks/{tid}/confirm", json={"user": "小李"})
print("1. 员工确认   →", r.json()["msg"])

# 2. 负责人确认（应成功）
r = httpx.post(f"{base}/api/tasks/{tid}/confirm", json={"user": "张总"})
print("2. 负责人确认 →", r.json()["msg"])

# 3. 员工协商（应成功）
r = httpx.post(f"{base}/api/tasks/{tid}/propose",
               json={"user": "小李", "new_content": "建议：外包给第三方设计公司"})
print("3. 员工协商   →", r.json()["msg"])

# 4. 员工审批自己的协商（应拒绝）
r = httpx.post(f"{base}/api/tasks/{tid}/approve", json={"user": "小李", "approve": True})
print("4. 员工审批   →", r.json()["msg"])

# 5. 负责人审批（应成功）
r = httpx.post(f"{base}/api/tasks/{tid}/approve", json={"user": "张总", "approve": True})
print("5. 负责人审批 →", r.json()["msg"])
