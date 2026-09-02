# -*- coding: utf-8 -*-
"""
app.py —— Web 后端（FastAPI）
统一暴露业务 API
"""
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import db
import auth
import agent
import chat
import graphrag
import knowledge
import memory
from splitter import split_project, set_cloud_key, is_cloud
from router import route

app = FastAPI(title="Scope Agent 权责分化系统")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载上传目录为静态文件（图片消息用）
import os
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# 启动时确保表存在 + 加载知识库
db.init_db()
auth.init_users()
chat.init_chat_db()
knowledge.load_knowledge()


# ---- 请求体模型（前端发来的 JSON 长这样）----
class ProjectIn(BaseModel):
    description: str


class ConfirmIn(BaseModel):
    user: str


class ProposeIn(BaseModel):
    user: str
    new_content: str


class ApproveIn(BaseModel):
    user: str
    approve: bool


# ---- API 端点 ----
@app.get("/", response_class=HTMLResponse)
def root():
    mode = "DeepSeek 云端" if is_cloud() else "本地 gemma4"
    return f"""
    <html><head><title>Scope Agent</title><meta charset="utf-8"></head>
    <body style="font-family:sans-serif;max-width:720px;margin:40px auto;line-height:1.7">
      <h1>Scope Agent 权责分化系统</h1>
      <p>当前 AI 模式：<b>{mode}</b></p>
      <hr>
      <h3>配置 DeepSeek（可选）</h3>
      <p>填了就切换到云端 DeepSeek；不填则用本地 gemma4。</p>
      <form method="post" action="/api/config/llm">
        <input type="text" name="api_key" placeholder="粘贴你的 DeepSeek API Key"
               style="width:100%;padding:8px;margin-bottom:8px">
        <button type="submit">保存并切换到 DeepSeek</button>
      </form>
      <p><a href="/docs">查看接口文档</a></p>
    </body></html>
    """


@app.post("/api/projects")
def create_project(p: ProjectIn):
    """创建项目：拆解 + 路由 + 入库"""
    tasks_json = split_project(p.description)
    simple, fuzzy = route(tasks_json)
    pid = db.save_project(p.description)
    db.save_tasks(pid, simple, fuzzy)
    return {"project_id": pid, "auto_assigned": len(simple), "pending_review": len(fuzzy)}


@app.get("/api/projects/{pid}/tasks")
def get_tasks(pid: int):
    """查某个项目的所有事项"""
    return {"tasks": db.query_tasks(pid)}


@app.post("/api/tasks/{tid}/confirm")
def confirm(tid: int, body: ConfirmIn):
    """负责人确认事项"""
    ok, msg = auth.confirm_task(tid, body.user)
    return {"ok": ok, "msg": msg}


@app.post("/api/tasks/{tid}/propose")
def propose(tid: int, body: ProposeIn):
    """员工协商"""
    ok, msg = auth.propose_change(tid, body.user, body.new_content)
    return {"ok": ok, "msg": msg}


@app.post("/api/tasks/{tid}/approve")
def approve(tid: int, body: ApproveIn):
    """负责人审批"""
    ok, msg = auth.approve_change(tid, body.user, body.approve)
    return {"ok": ok, "msg": msg}


# ---- 聊天端点 ----
class ChatIn(BaseModel):
    type: str                      # 'direct' 私聊 / 'group' 群聊
    name: str = None
    member_ids: list[int] = []


class MessageIn(BaseModel):
    token: str
    content: str
    msg_type: str = "text"
    lat: float = None
    lng: float = None


@app.post("/api/chats")
def create_chat(body: ChatIn):
    """创建会话（私聊/群聊）"""
    cid = chat.create_chat(body.type, body.name, tuple(body.member_ids))
    return {"chat_id": cid}


@app.get("/api/chats/user/{uid}")
def user_chats(uid: int):
    """当前用户的会话列表（含最新消息、未读）"""
    return {"chats": chat.get_user_chats(uid)}


@app.post("/api/chats/{cid}/messages")
def post_message(cid: int, body: MessageIn):
    """发消息（支持 text / location，用 token 识别身份）"""
    user = auth.get_user_by_token(body.token)
    if not user:
        return {"ok": False, "msg": "未登录或 token 无效"}
    chat.send_message(cid, user["id"], body.content, body.msg_type, body.lat, body.lng)
    return {"ok": True, "msg": "已发送"}


class WithdrawIn(BaseModel):
    token: str


@app.post("/api/messages/{mid}/withdraw")
def withdraw(mid: int, body: WithdrawIn):
    """撤回消息（2分钟内、只能撤回自己的）"""
    user = auth.get_user_by_token(body.token)
    if not user:
        return {"ok": False, "msg": "未登录或 token 无效"}
    ok, msg = chat.withdraw_message(mid, user["id"])
    return {"ok": ok, "msg": msg}


@app.get("/api/chats/{cid}/messages")
def get_chat_messages(cid: int):
    """获取会话消息"""
    return {"messages": chat.get_messages(cid)}


class AgentChatIn(BaseModel):
    message: str
    user_id: int = None
    system: str = None


@app.post("/api/agent/chat")
def agent_chat(body: AgentChatIn):
    """员工和 AI 对话（agent，含用户画像记忆 + RAG + 项目完成树）"""
    base_prompt = (
        "你是项目规划助手。涉及项目具体信息时用 search_knowledge 查知识库；"
        "用户要求生成项目完成树时用 create_task_tree；需要发消息时用 send_message。")
    # 注入用户画像记忆
    if body.user_id:
        user_memory = memory.get_memory(body.user_id)
        if user_memory and user_memory != "{}":
            base_prompt += f"\n\n【用户画像】{user_memory}"
    sys_prompt = body.system or base_prompt
    answer, rounds = agent.run_agent(body.message, sys_prompt)
    # 对话后更新用户画像记忆
    if body.user_id:
        memory.update_memory(body.user_id, f"用户说：{body.message}\nAI：{answer}")
    return {"answer": answer, "rounds": rounds}


@app.post("/api/config/llm")
def config_llm(api_key: str = Form(...)):
    """用户提交 DeepSeek API key，切换到云端模式"""
    set_cloud_key(api_key)
    return {"ok": True, "msg": "已切换到 DeepSeek 云端", "mode": "cloud"}


@app.post("/api/config/graphrag")
def config_graphrag(enabled: bool = Form(...)):
    """客户可选择 GraphRAG（图增强 RAG）开关"""
    graphrag.set_enabled(enabled)
    return {"ok": True, "msg": "GraphRAG 已启用" if enabled else "GraphRAG 已关闭"}


class RegisterIn(BaseModel):
    name: str
    password: str
    role: str = "user"


class LoginIn(BaseModel):
    name: str
    password: str


@app.post("/api/register")
def register(body: RegisterIn):
    """用户注册"""
    ok, msg = auth.register(body.name, body.password, body.role)
    return {"ok": ok, "msg": msg}


@app.post("/api/login")
def login(body: LoginIn):
    """用户登录，返回 token"""
    token, result = auth.login(body.name, body.password)
    if token:
        return {"ok": True, "token": token,
                "user": {"id": result["id"], "name": result["name"], "role": result["role"]}}
    return {"ok": False, "msg": result}


class FriendIn(BaseModel):
    user_id: int
    target_id: int
    requester_role: str


class FriendApproveIn(BaseModel):
    approve: bool
    approver_role: str


@app.post("/api/friends/add")
def add_friend(body: FriendIn):
    """加好友（员工加负责人直接通过；员工之间需负责人审核）"""
    target = auth.get_user_by_id(body.target_id)
    if not target:
        return {"ok": False, "msg": "目标用户不存在"}
    status = chat.add_friend(body.user_id, body.target_id, body.requester_role, target["role"])
    return {"ok": True, "status": status}


@app.get("/api/friends/pending")
def pending_friends():
    """查待审核的好友申请（负责人用）"""
    return {"pending": chat.pending_friendships()}


@app.post("/api/friends/{fid}/approve")
def approve_friend(fid: int, body: FriendApproveIn):
    """负责人审核好友申请"""
    ok, msg = chat.approve_friend(fid, body.approve, body.approver_role)
    return {"ok": ok, "msg": msg}


@app.get("/api/friends/{uid}")
def friends_list(uid: int):
    """查某人的好友列表"""
    return {"friends": chat.get_friends(uid)}


class KnowledgeIn(BaseModel):
    texts: list[str]


@app.post("/api/knowledge/build")
def build_knowledge(body: KnowledgeIn):
    """构建/重建项目知识库，返回条数"""
    n = knowledge.build_knowledge(body.texts)
    return {"ok": True, "count": n}


@app.post("/api/projects/{pid}/upload")
async def upload(pid: int, user: str = Form(...), file: UploadFile = File(...)):
    """负责人上传资料"""
    u = auth.get_user(user)
    if not u or u["role"] != "manager":
        return {"ok": False, "msg": "权限不足：只有负责人能上传"}
    import os
    os.makedirs("uploads", exist_ok=True)
    path = os.path.join("uploads", file.filename)
    with open(path, "wb") as f:
        f.write(await file.read())          # 保存文件到 uploads/
    fid = chat.upload_file(pid, file.filename, path, u["id"])
    return {"ok": True, "msg": "上传成功", "file_id": fid}


@app.post("/api/friends/{fid}/files")
async def send_file(fid: int, user_token: str = Form(...), file: UploadFile = File(...)):
    """传文件给好友（仅好友之间可传）"""
    user = auth.get_user_by_token(user_token)
    if not user:
        return {"ok": False, "msg": "未登录或 token 无效"}
    if not chat.is_friend(user["id"], fid):
        return {"ok": False, "msg": "仅好友之间可传文件"}
    import os
    os.makedirs("uploads", exist_ok=True)
    path = os.path.join("uploads", file.filename)
    with open(path, "wb") as f:
        f.write(await file.read())
    file_id = chat.upload_file(0, file.filename, path, user["id"])
    return {"ok": True, "msg": "已传文件", "file_id": file_id}


@app.post("/api/chats/{cid}/image")
async def send_image(cid: int, token: str = Form(...), file: UploadFile = File(...)):
    """发送图片消息"""
    user = auth.get_user_by_token(token)
    if not user:
        return {"ok": False, "msg": "未登录或 token 无效"}
    os.makedirs("uploads", exist_ok=True)
    path = os.path.join("uploads", file.filename)
    with open(path, "wb") as f:
        f.write(await file.read())
    chat.send_message(cid, user["id"], f"/uploads/{file.filename}", "image")
    return {"ok": True, "msg": "已发送图片"}


if __name__ == "__main__":
    import os
    import uvicorn
    # 默认本机访问；内网部署设 HOST=0.0.0.0 即可让内网其他电脑访问
    host = os.environ.get("HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=8000)
