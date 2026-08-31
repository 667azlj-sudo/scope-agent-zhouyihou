# -*- coding: utf-8 -*-
"""test_all.py —— 完整功能验证"""
import sqlite3

import httpx

base = "http://127.0.0.1:8000"
fails = []


def log(name, ok, extra=""):
    print(f"{'✅' if ok else '❌'} {name} {extra}")
    if not ok:
        fails.append(name)


def uid(name):
    conn = sqlite3.connect("scope_agent.db")
    row = conn.execute("SELECT id FROM users WHERE name=?", (name,)).fetchone()
    conn.close()
    return row[0] if row else None


# 1. 注册 + 登录
log("注册负责人", httpx.post(base + "/api/register", json={"name": "张总", "password": "123456", "role": "manager"}).json()["ok"])
log("注册员工李四", httpx.post(base + "/api/register", json={"name": "李四", "password": "123456", "role": "employee"}).json()["ok"])
log("注册员工王五", httpx.post(base + "/api/register", json={"name": "王五", "password": "123456", "role": "employee"}).json()["ok"])
tok = httpx.post(base + "/api/login", json={"name": "张总", "password": "123456"}).json()
log("登录张总拿token", "token" in tok)
tok_zhang = tok["token"]
tok_li = httpx.post(base + "/api/login", json={"name": "李四", "password": "123456"}).json()["token"]

# 2. 加好友（员工→负责人直接通过；员工→员工需审核）
log("李四加张总(直接通过)", httpx.post(base + "/api/friends/add", json={"user_id": uid("李四"), "target_id": uid("张总"), "requester_role": "employee"}).json()["status"] == "approved")
log("李四加王五(需审核)", httpx.post(base + "/api/friends/add", json={"user_id": uid("李四"), "target_id": uid("王五"), "requester_role": "employee"}).json()["status"] == "pending")
pending = httpx.get(base + "/api/friends/pending").json()["pending"]
fid = pending[0]["id"]
log("负责人审核好友", httpx.post(base + f"/api/friends/{fid}/approve", json={"approve": True, "approver_role": "manager"}).json()["ok"])

# 3. 聊天（token 认证）
cid = httpx.post(base + "/api/chats", json={"type": "group", "name": "项目组", "member_ids": [uid("张总"), uid("李四"), uid("王五")]}).json()["chat_id"]
log("创建群聊", bool(cid))
log("用token发消息", httpx.post(base + f"/api/chats/{cid}/messages", json={"token": tok_zhang, "content": "大家好"}).json()["ok"])
log("获取群聊消息", len(httpx.get(base + f"/api/chats/{cid}/messages").json()["messages"]) > 0)

# 4. 知识库 + agent 对话（RAG）
log("构建知识库", httpx.post(base + "/api/knowledge/build", json={"texts": ["项目预算10万，工期一个月", "官网包含首页、产品展示、新闻"]}).json()["ok"])
r = httpx.post(base + "/api/agent/chat", json={"message": "这个项目的预算多少？", "user_id": uid("李四")}, timeout=300)
log("agent对话(查知识库)", "10万" in r.json()["answer"], r.json()["answer"][:40])

# 5. GraphRAG 开关
log("开启GraphRAG", httpx.post(base + "/api/config/graphrag", data={"enabled": True}).json()["ok"])

# 6. 创建项目（AI 拆解）
r = httpx.post(base + "/api/projects", json={"description": "开发一个企业官网"}, timeout=300).json()
log("创建项目(AI拆解)", "project_id" in r, str(r.get("auto_assigned", "?")) + "自动/" + str(r.get("pending_review", "?")) + "待确认")
pid = r.get("project_id")

# 7. 权限审批（员工拒、负责人过）
tasks = httpx.get(base + f"/api/projects/{pid}/tasks").json()["tasks"]
t = tasks[0] if tasks else None
if t:
    log("员工确认(应拒)", not httpx.post(base + f"/api/tasks/{t['id']}/confirm", json={"user": "李四"}).json()["ok"])
    log("负责人确认(应过)", httpx.post(base + f"/api/tasks/{t['id']}/confirm", json={"user": "张总"}).json()["ok"])

# 8. 记忆（agent 跨对话画像）
log("记忆-用户画像更新", bool(httpx.post(base + "/api/agent/chat", json={"message": "我喜欢用Python", "user_id": uid("李四")}, timeout=300).json()["rounds"]))

print("\n==== 结果 ====")
print("🎉 全部通过" if not fails else f"❌ 失败项: {fails}")
