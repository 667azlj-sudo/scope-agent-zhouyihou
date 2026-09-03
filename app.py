# -*- coding: utf-8 -*-
"""
app.py —— Web 后端（FastAPI）
统一暴露业务 API
"""
from fastapi import FastAPI, UploadFile, File, Form, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import os
import uuid

import config
import db
import auth
import chat
import company
import graphrag
import knowledge
import ability_kb
import llm
import memory
import sms
import payment
import personal_rag
import agent_framework as af
from splitter import split_project, set_cloud_key, is_cloud
from router import route

app = FastAPI(title="Scope Agent 权责分化系统")

_allowed_origins = [
    o.strip()
    for o in os.environ.get(
        "ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- 鉴权：除白名单外的 /api/* 都要求登录 ----
# 注意：/api/config/llm 会改全局云端 Key，必须登录 + 负责人角色，不能放公开白名单。
PUBLIC_API_PATHS = {"/api/login", "/api/register", "/api/sms/send"}


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path.rstrip("/")
    if path.startswith("/api/") and path not in PUBLIC_API_PATHS:
        user = auth.get_user_by_token(auth.parse_bearer(request.headers.get("authorization", "")))
        if not user:
            return JSONResponse({"ok": False, "msg": "未登录或登录已过期"}, status_code=401)
        request.state.user = user
    return await call_next(request)


def _current_user(request: Request):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return user


def require_role(*roles):
    """依赖工厂：要求当前登录用户属于指定角色。"""
    def checker(request: Request):
        user = getattr(request.state, "user", None)
        if not user:
            raise HTTPException(status_code=401, detail="未登录")
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="权限不足")
        return user
    return checker


def _self_uid(user: dict, uid: int):
    """个人数据保护：非经理强制使用本人 id；经理仅能访问本公司成员。"""
    if user["role"] != "manager":
        return user["id"]
    target = auth.get_user_by_id(uid)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")
    if target.get("company_id") != user.get("company_id"):
        raise HTTPException(status_code=403, detail="无权访问其他公司数据")
    return uid


def _require_company_task(task_id: int, user: dict):
    """校验任务属于当前用户（经理）本公司，否则 403。返回任务 dict。"""
    task = af.get_agent_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if af._task_company_id(task) != user.get("company_id"):
        raise HTTPException(status_code=403, detail="无权操作其他公司任务")
    return task


def _require_company_submission(submission_id: int, user: dict):
    """校验提交属于当前用户（经理）本公司，否则 403。返回提交 dict。"""
    sub = af.get_submission(submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="提交不存在")
    task = af.get_agent_task(sub["task_id"])
    if not task or af._task_company_id(task) != user.get("company_id"):
        raise HTTPException(status_code=403, detail="无权操作其他公司提交")
    return sub


# 挂载上传目录为静态文件（图片消息用）
config.ensure_dirs()
app.mount("/uploads", StaticFiles(directory=config.UPLOAD_DIR), name="uploads")

# ---- 上传安全：文件名白名单 + 大小限制 ----
ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
ALLOWED_TEXT_EXTS = {".txt", ".md", ".log", ".csv", ".json"}
ALLOWED_FILE_EXTS = ALLOWED_IMAGE_EXTS | ALLOWED_TEXT_EXTS | {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip"}
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)) or "0") or (20 * 1024 * 1024)


def _safe_upload_filename(filename, allowed_exts, fallback_ext=".bin"):
    """生成安全的落盘文件名：丢弃一切路径成分，只保留白名单扩展名，用 uuid 命名。"""
    name = os.path.basename((filename or "").replace("\\", "/"))
    ext = os.path.splitext(name)[1].lower()
    if ext not in allowed_exts:
        ext = fallback_ext
    return f"{uuid.uuid4().hex[:16]}{ext}"


async def _read_upload_bytes(file):
    """读取上传内容并做大小限制；超限抛 ValueError。"""
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("文件过大")
    return data

# 生产环境守卫：短信未配置真实通道时，验证码会退化为明文返回，注册形同虚设。
# 设置 REQUIRE_SMS=1 强制要求配置阿里云短信，否则拒绝启动。
if (os.environ.get("REQUIRE_SMS", "") or "").strip() in ("1", "true", "yes") and not sms.configured():
    raise RuntimeError("REQUIRE_SMS=1 但未配置阿里云短信密钥，拒绝启动")

# 启动时确保表存在 + 加载知识库 + 从环境变量加载云端 LLM key
db.init_db()
af.init_agent_db()
auth.init_users()
company.init_company_db()
chat.init_chat_db()
payment.init_payment_db()
knowledge.load_knowledge()
llm.load_cloud_from_env()


# ---- 请求体模型（前端发来的 JSON 长这样）----
class ProjectIn(BaseModel):
    description: str


class ConfirmIn(BaseModel):
    pass


class ProposeIn(BaseModel):
    new_content: str


class ApproveIn(BaseModel):
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
def confirm(tid: int, body: ConfirmIn, user: dict = Depends(require_role("manager"))):
    """负责人确认事项（身份取自登录态，不再信任请求体中的用户名）"""
    ok, msg = auth.confirm_task(tid, user["name"])
    return {"ok": ok, "msg": msg}


@app.post("/api/tasks/{tid}/propose")
def propose(tid: int, body: ProposeIn, user: dict = Depends(_current_user)):
    """员工协商（身份取自登录态）"""
    ok, msg = auth.propose_change(tid, user["name"], body.new_content)
    return {"ok": ok, "msg": msg}


@app.post("/api/tasks/{tid}/approve")
def approve(tid: int, body: ApproveIn, user: dict = Depends(require_role("manager"))):
    """负责人审批（身份取自登录态）"""
    ok, msg = auth.approve_change(tid, user["name"], body.approve)
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
def create_chat(body: ChatIn, user: dict = Depends(_current_user)):
    """创建会话（私聊/群聊），创建者自动计入成员"""
    mids = list(body.member_ids)
    if user["id"] not in mids:
        mids.append(user["id"])
    cid = chat.create_chat(body.type, body.name, tuple(mids))
    return {"chat_id": cid}


@app.get("/api/chats/user/{uid}")
def user_chats(uid: int, user: dict = Depends(_current_user)):
    """当前用户的会话列表（含最新消息、未读）"""
    uid = _self_uid(user, uid)
    return {"chats": chat.get_user_chats(uid)}


@app.post("/api/chats/{cid}/messages")
def post_message(cid: int, body: MessageIn):
    """发消息（支持 text / location，用 token 识别身份）"""
    user = auth.get_user_by_token(body.token)
    if not user:
        return {"ok": False, "msg": "未登录或 token 无效"}
    if not chat.is_chat_member(cid, user["id"]):
        return {"ok": False, "msg": "你不在该会话中"}
    chat.send_message(cid, user["id"], body.content, body.msg_type, body.lat, body.lng)
    return {"ok": True, "msg": "已发送"}


class WithdrawIn(BaseModel):
    token: str


class MarkReadIn(BaseModel):
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
def get_chat_messages(cid: int, user: dict = Depends(_current_user)):
    """获取会话消息（仅会话成员可见）"""
    if not chat.is_chat_member(cid, user["id"]):
        raise HTTPException(status_code=403, detail="你不在该会话中")
    return {"messages": chat.get_messages(cid)}


@app.post("/api/chats/{cid}/read")
def mark_chat_read(cid: int, body: MarkReadIn):
    """标记会话已读（消除红点）"""
    user = auth.get_user_by_token(body.token)
    if not user:
        return {"ok": False, "msg": "未登录或 token 无效"}
    if not chat.is_chat_member(cid, user["id"]):
        return {"ok": False, "msg": "你不在该会话中"}
    chat.mark_read(cid, user["id"])
    return {"ok": True, "msg": "已读"}


@app.post("/api/config/llm")
def config_llm(api_key: str = Form(""), user: dict = Depends(require_role("manager"))):
    """负责人设置 DeepSeek API key（全局配置，须登录 + 负责人角色）"""
    is_cloud_now = llm.persist_cloud_key(api_key)
    return {"ok": True, "msg": "已切换到 DeepSeek 云端" if is_cloud_now else "已回退本地模式",
            "mode": "cloud" if is_cloud_now else "local"}


@app.get("/api/config/llm")
def config_llm_status():
    """当前 LLM 模式"""
    return {"mode": "cloud" if is_cloud() else "local"}


@app.post("/api/config/graphrag")
def config_graphrag(enabled: bool = Form(...)):
    """客户可选择 GraphRAG（图增强 RAG）开关"""
    graphrag.set_enabled(enabled)
    return {"ok": True, "msg": "GraphRAG 已启用" if enabled else "GraphRAG 已关闭"}


class RegisterIn(BaseModel):
    name: str
    password: str
    role: str             # 岗位必填，不能默认
    phone: str = ""       # 手机号（需已通过验证码校验）
    code: str = ""        # 短信验证码
    company_name: str = ""  # 经理注册时填公司名
    invite_code: str = ""   # 员工注册时填公司邀请码
    position: str = ""      # 公司岗位


class LoginIn(BaseModel):
    account: str       # 用户名或手机号
    password: str


class SmsSendIn(BaseModel):
    phone: str


@app.post("/api/sms/send")
def send_sms(body: SmsSendIn):
    """发送短信验证码。未配置阿里云密钥时走模拟模式，验证码一并返回。"""
    from auth import _normalize_phone
    phone = _normalize_phone(body.phone)
    if not phone:
        return {"ok": False, "msg": "手机号格式不正确"}
    can_send, send_err = auth.can_send_code(phone)
    if not can_send:
        return {"ok": False, "msg": send_err}
    code = auth.create_verify_code(phone)
    ok, mock, msg = sms.send_sms(phone, code)
    if not ok:
        return {"ok": False, "msg": msg}
    resp = {"ok": True, "msg": msg, "mock": mock}
    if mock:
        resp["code"] = code  # 仅模拟模式返回，方便本地联调
    return resp


@app.post("/api/register")
def register(body: RegisterIn):
    """用户注册：手机号验证码 + 公司归属 + 岗位；注册成功自动建 Agent"""
    from auth import _normalize_phone
    phone = _normalize_phone(body.phone)
    if not phone:
        return {"ok": False, "msg": "手机号格式不正确"}
    ok_code, msg_code = auth.verify_code(phone, body.code)
    if not ok_code:
        return {"ok": False, "msg": msg_code}

    # 公司归属处理：所有人必须选岗位；经理建公司，其他人（员工/普通成员）凭邀请码加入
    company_id = None
    if not body.position.strip():
        return {"ok": False, "msg": "请选择岗位"}
    if body.role == "manager":
        if not body.company_name.strip():
            return {"ok": False, "msg": "请填写公司名称"}
    else:
        # 员工 / 普通成员：都必须凭经理邀请码加入公司
        if not body.invite_code.strip():
            return {"ok": False, "msg": "请填写公司邀请码"}
        c = company.get_company_by_code(body.invite_code)
        if not c:
            return {"ok": False, "msg": "邀请码无效"}
        company_id = c["id"]

    ok, msg = auth.register(body.name, body.password, body.role, phone, company_id, body.position.strip())
    if not ok:
        return {"ok": False, "msg": msg}

    user = auth.get_user(body.name) or (auth.get_user_by_phone(phone) if phone else None)

    # 经理：注册后创建公司并回填负责人 + 建总公司群
    if body.role == "manager" and user:
        comp, err = company.create_company(body.company_name.strip(), user["id"])
        if not comp:
            return {"ok": False, "msg": err}
        from auth import get_conn as _ac
        _c = _ac()
        _c.execute("UPDATE users SET company_id=? WHERE id=?", (comp["id"], user["id"]))
        _c.commit()
        _c.close()
        # 建总公司群并把经理拉进去
        cid = chat.create_company_chat(comp["id"])
        chat.add_chat_member(cid, user["id"])
        company_id = comp["id"]

    # 员工 / 普通成员：加入公司后自动进总公司群
    if body.role in ("employee", "user") and user and company_id:
        cc = chat.get_company_chat(company_id)
        if cc:
            chat.add_chat_member(cc["id"], user["id"])

    # 自动为所有人建专属 Agent（不替用户干活，只做审核/报价/协作）。
    # 普通成员(user)也建 Agent，映射为 employee 角色，便于接外包单子。
    if user:
        try:
            agent_role = body.role if body.role != "user" else "employee"
            af.create_agent(user["id"], agent_role, f"{body.name} 的 Agent")
        except Exception:  # noqa: BLE001
            pass
    return {"ok": True, "msg": "注册成功"}


@app.post("/api/login")
def login(body: LoginIn):
    """用户登录（账号 = 用户名或手机号），返回 token"""
    token, result = auth.login(body.account, body.password)
    if token:
        return {"ok": True, "token": token,
                "user": {"id": result["id"], "name": result["name"], "role": result["role"],
                         "company_id": result.get("company_id"), "position": result.get("position")}}
    return {"ok": False, "msg": result}


class LogoutIn(BaseModel):
    token: str


@app.post("/api/logout")
def logout(body: LogoutIn):
    """退出登录，使 token 失效"""
    auth.logout(body.token)
    return {"ok": True, "msg": "已退出登录"}


class FriendIn(BaseModel):
    user_id: int
    target_id: int
    requester_role: str


class FriendApproveIn(BaseModel):
    approve: bool
    approver_role: str


@app.post("/api/friends/add")
def add_friend(body: FriendIn, user: dict = Depends(_current_user)):
    """加好友（员工加负责人直接通过；员工之间需负责人审核）"""
    target = auth.get_user_by_id(body.target_id)
    if not target:
        return {"ok": False, "msg": "目标用户不存在"}
    status = chat.add_friend(user["id"], body.target_id, user["role"], target["role"])
    return {"ok": True, "status": status}


@app.get("/api/friends/pending")
def pending_friends(user: dict = Depends(require_role("manager"))):
    """查待审核的好友申请（负责人用）"""
    return {"pending": chat.pending_friendships()}


@app.post("/api/friends/{fid}/approve")
def approve_friend(fid: int, body: FriendApproveIn, user: dict = Depends(require_role("manager"))):
    """负责人审核好友申请"""
    ok, msg = chat.approve_friend(fid, body.approve, user["role"])
    return {"ok": ok, "msg": msg}


@app.get("/api/friends/{uid}")
def friends_list(uid: int, user: dict = Depends(_current_user)):
    """查某人的好友列表"""
    uid = _self_uid(user, uid)
    return {"friends": chat.get_friends(uid)}


class KnowledgeIn(BaseModel):
    texts: list[str]


@app.post("/api/knowledge/build")
def build_knowledge(body: KnowledgeIn):
    """构建/重建项目知识库，返回条数"""
    n = knowledge.build_knowledge(body.texts)
    return {"ok": True, "count": n}


@app.post("/api/projects/{pid}/upload")
async def upload(pid: int, file: UploadFile = File(...), user: dict = Depends(require_role("manager"))):
    """负责人上传资料（身份取自登录态）"""
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    try:
        data = await _read_upload_bytes(file)
    except ValueError:
        return {"ok": False, "msg": f"文件过大（上限 {MAX_UPLOAD_BYTES // (1024*1024)}MB）"}
    path = os.path.join(config.UPLOAD_DIR, _safe_upload_filename(file.filename, ALLOWED_FILE_EXTS))
    with open(path, "wb") as f:
        f.write(data)
    fid = chat.upload_file(pid, os.path.basename(file.filename or ""), path, user["id"])
    return {"ok": True, "msg": "上传成功", "file_id": fid}


@app.post("/api/friends/{fid}/files")
async def send_file(fid: int, user_token: str = Form(...), file: UploadFile = File(...)):
    """传文件给好友（仅好友之间可传）"""
    user = auth.get_user_by_token(user_token)
    if not user:
        return {"ok": False, "msg": "未登录或 token 无效"}
    if not chat.is_friend(user["id"], fid):
        return {"ok": False, "msg": "仅好友之间可传文件"}
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    try:
        data = await _read_upload_bytes(file)
    except ValueError:
        return {"ok": False, "msg": f"文件过大（上限 {MAX_UPLOAD_BYTES // (1024*1024)}MB）"}
    path = os.path.join(config.UPLOAD_DIR, _safe_upload_filename(file.filename, ALLOWED_FILE_EXTS))
    with open(path, "wb") as f:
        f.write(data)
    file_id = chat.upload_file(0, os.path.basename(file.filename or ""), path, user["id"])
    return {"ok": True, "msg": "已传文件", "file_id": file_id}


@app.post("/api/chats/{cid}/image")
async def send_image(cid: int, token: str = Form(...), file: UploadFile = File(...)):
    """发送图片消息"""
    user = auth.get_user_by_token(token)
    if not user:
        return {"ok": False, "msg": "未登录或 token 无效"}
    if not chat.is_chat_member(cid, user["id"]):
        return {"ok": False, "msg": "你不在该会话中"}
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    try:
        data = await _read_upload_bytes(file)
    except ValueError:
        return {"ok": False, "msg": f"文件过大（上限 {MAX_UPLOAD_BYTES // (1024*1024)}MB）"}
    filename = _safe_upload_filename(file.filename, ALLOWED_IMAGE_EXTS, ".jpg")
    path = os.path.join(config.UPLOAD_DIR, filename)
    with open(path, "wb") as f:
        f.write(data)
    chat.send_message(cid, user["id"], f"/uploads/{filename}", "image")
    return {"ok": True, "msg": "已发送图片", "url": f"/uploads/{filename}"}


# ---- 多 Agent 协作（agent_framework）----
class CreateAgentIn(BaseModel):
    role_type: str
    name: str
    config: dict = None          # 可选，JSON 对象


class SplitTaskIn(BaseModel):
    title: str
    detail: str
    manager_agent_id: int = None


class ClassifyTaskIn(BaseModel):
    choice: str   # internal=机密→内部分配 / outsource=一般→外包候选


class AssignTaskIn(BaseModel):
    task_id: int
    agent_id: int


class EstimateTaskIn(BaseModel):
    task_id: int
    agent_id: int


class ReviewEstimateIn(BaseModel):
    approve: bool
    custom_wage: float = None   # 经理手动改价（可选）


class SaveRecordIn(BaseModel):
    content: str


class SubmitWorkIn(BaseModel):
    task_id: int
    agent_id: int
    content: str
    images: list[str] = []   # 照片凭证 URL 列表


class ReviewSubmissionIn(BaseModel):
    approve: bool
    exempt: bool = None          # 可选，1=按基础工资豁免绩效
    custom_price: float = None   # 经理手动改价（可选）


class SetSalaryIn(BaseModel):
    base_salary: float
    exempt: bool


@app.post("/api/agents/{user_id}/create")
def create_agent(user_id: int, body: CreateAgentIn, user: dict = Depends(require_role("manager"))):
    """为员工建立 Agent（仅本公司员工，user_id 唯一）"""
    target = auth.get_user_by_id(user_id)
    if not target:
        return {"ok": False, "msg": "用户不存在"}
    if target.get("company_id") != user.get("company_id"):
        raise HTTPException(status_code=403, detail="只能为本公司员工建 Agent")
    agent = af.create_agent(user_id, body.role_type, body.name, body.config)
    return {"agent_id": agent["id"]}


@app.post("/api/tasks/split")
def split_task(body: SplitTaskIn, user: dict = Depends(require_role("manager"))):
    """让 LLM 把任务拆成子任务并入库"""
    subtasks = af.split_task(body.title, body.detail, body.manager_agent_id)
    return {"subtasks": subtasks}


@app.post("/api/tasks/file")
async def upload_task_file(file: UploadFile = File(...)):
    """新建任务时上传参考文件：保存并解析文本，供拆解时并入描述。"""
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    try:
        data = await _read_upload_bytes(file)
    except ValueError:
        return {"ok": False, "msg": f"文件过大（上限 {MAX_UPLOAD_BYTES // (1024*1024)}MB）"}
    filename = _safe_upload_filename(file.filename, ALLOWED_FILE_EXTS, ".txt")
    path = os.path.join(config.UPLOAD_DIR, filename)
    with open(path, "wb") as f:
        f.write(data)
    text = _read_text_bytes(data).strip()[:5000]
    return {"ok": True, "url": f"/uploads/{filename}", "filename": os.path.basename(file.filename or ""), "text": text}


@app.get("/api/tasks/pending-classify")
def pending_classify(user: dict = Depends(require_role("manager"))):
    """经理看待确认分级（pending_classify）的子任务列表"""
    return {"tasks": af.get_pending_classification(user.get("company_id"))}


@app.post("/api/tasks/{tid}/classify")
def classify(tid: int, body: ClassifyTaskIn, user: dict = Depends(require_role("manager"))):
    """经理选择分级：internal=机密→内部分配 / outsource=一般→外包候选"""
    _require_company_task(tid, user)
    return af.manager_choose(tid, body.choice)


@app.post("/api/tasks/distribute")
def distribute_task(body: AssignTaskIn, user: dict = Depends(require_role("manager"))):
    """经理 agent 把内部任务分发给某个员工 agent（distributed）"""
    _require_company_task(body.task_id, user)
    return af.distribute_task(body.agent_id, body.task_id)


@app.post("/api/tasks/estimate")
def estimate_task(body: EstimateTaskIn, user: dict = Depends(_current_user)):
    """员工 agent 审核任务并报价（结合本地记录给工时+工资）"""
    agent = af.get_agent_by_user(user["id"])
    if not agent or agent["id"] != body.agent_id:
        return {"ok": False, "msg": "只能用自己的 Agent 报价"}
    return af.estimate_task(body.agent_id, body.task_id)


@app.post("/api/tasks/{tid}/review-estimate")
def review_estimate(tid: int, body: ReviewEstimateIn, user: dict = Depends(require_role("manager"))):
    """经理 agent 审核报价：通过→正式派发(改价则待员工确认) / 打回→重新报价"""
    _require_company_task(tid, user)
    return af.review_estimate(tid, body.approve, body.custom_wage)


class ConfirmPriceIn(BaseModel):
    user_id: int
    agree: bool


@app.post("/api/tasks/{tid}/confirm-price")
def confirm_price(tid: int, body: ConfirmPriceIn, user: dict = Depends(_current_user)):
    """员工确认经理改价：同意→派发 / 不同意→返回经理重新定价"""
    return af.employee_confirm_price(tid, user["id"], body.agree)


@app.get("/api/tasks/internal")
def internal_tasks(user: dict = Depends(require_role("manager"))):
    """经理看待分发的内部任务（本公司）"""
    return {"tasks": af.get_internal_tasks(user.get("company_id"))}


@app.get("/api/tasks/estimated")
def estimated_tasks(user: dict = Depends(require_role("manager"))):
    """经理看待审核报价的任务（本公司）"""
    return {"tasks": af.get_estimated_tasks(user.get("company_id"))}


class PublishHallIn(BaseModel):
    candidate_ids: list[int]


class ClaimTaskIn(BaseModel):
    user_id: int


@app.get("/api/tasks/unmatched")
def unmatched_tasks(user: dict = Depends(require_role("manager"))):
    """经理端：无人接手的任务（本公司）"""
    return {"tasks": af.get_unmatched_tasks(user.get("company_id"))}


@app.post("/api/tasks/{tid}/publish-hall")
def publish_hall(tid: int, body: PublishHallIn, user: dict = Depends(require_role("manager"))):
    """经理选候选人后发布到任务大厅"""
    _require_company_task(tid, user)
    return af.publish_to_hall(tid, body.candidate_ids)


@app.get("/api/hall/{uid}")
def hall_tasks(uid: int, user: dict = Depends(_current_user)):
    """任务大厅：该用户作为候选人的待接取任务"""
    uid = _self_uid(user, uid)
    return {"tasks": af.get_hall_tasks(uid)}


@app.post("/api/hall/{tid}/claim")
def claim_task(tid: int, body: ClaimTaskIn, user: dict = Depends(_current_user)):
    """候选人接取大厅任务"""
    return af.claim_task(tid, user["id"])


class AcceptOutsourceIn(BaseModel):
    user_id: int


class PayDepositIn(BaseModel):
    pass


@app.get("/api/outsource")
def outsource_tasks(user: dict = Depends(_current_user)):
    """外包大厅：所有待接取的外包任务（跨公司），附押金与本人缴纳状态"""
    return {"tasks": af.get_outsource_tasks(user["id"])}


@app.post("/api/outsource/{tid}/deposit")
def pay_outsource_deposit(tid: int, body: PayDepositIn, user: dict = Depends(_current_user)):
    """缴纳外包任务押金（缴纳后才有资格接取）"""
    return af.pay_outsource_deposit(tid, user["id"])


@app.post("/api/outsource/{tid}/accept")
def accept_outsource(tid: int, body: AcceptOutsourceIn, user: dict = Depends(_current_user)):
    """缴押金后接取外包任务（所有人可接）"""
    return af.accept_outsource(tid, user["id"])


@app.get("/api/agents")
def list_agents(user: dict = Depends(_current_user)):
    """本公司 Agent（经理分发时选择）"""
    cid = user.get("company_id")
    return {"agents": [a for a in af.list_agents() if not cid or a.get("company_id") == cid]}


@app.get("/api/users")
def list_users(user: dict = Depends(_current_user)):
    """本公司用户（建群/拉人时选择成员用）"""
    cid = user.get("company_id")
    return {"users": [
        {"id": u["id"], "name": u["name"], "role": u["role"],
         "position": u.get("position"), "company_id": u.get("company_id")}
        for u in auth.get_all_users()
        if not cid or u.get("company_id") == cid
    ]}


@app.get("/api/companies")
def list_companies(user: dict = Depends(require_role("manager"))):
    """公司列表（仅返回本公司，负责人用）"""
    cid = user.get("company_id")
    comp = company.get_company(cid) if cid else None
    return {"companies": [comp] if comp else []}


@app.get("/api/companies/by-code")
def company_by_code(code: str):
    """按邀请码查公司（仅返回公司名与邀请码，供注册加入用）"""
    c = company.get_company_by_code(code)
    if not c:
        return None
    return {"id": c["id"], "name": c["name"], "invite_code": c["invite_code"]}


@app.get("/api/companies/{cid}")
def company_detail(cid: int, user: dict = Depends(_current_user)):
    """公司详情：基本信息 + 邀请码 + 成员列表（仅本公司成员可见）"""
    if user.get("company_id") != cid:
        return {"ok": False, "msg": "无权查看该公司"}
    comp = company.get_company(cid)
    if not comp:
        return {"ok": False, "msg": "公司不存在"}
    return {"ok": True, "company": comp, "members": company.get_company_members(cid)}


@app.get("/api/records/{uid}")
def get_records(uid: int, user: dict = Depends(_current_user)):
    """员工本地记录（个人档案/技能/历史绩效）"""
    uid = _self_uid(user, uid)
    return af.get_user_records(uid)


@app.post("/api/records/{uid}")
def save_records(uid: int, body: SaveRecordIn, user: dict = Depends(_current_user)):
    """保存员工本地记录"""
    uid = _self_uid(user, uid)
    return af.save_user_records(uid, body.content)


# ---- 知识库①：工作记录 ----
class WorkRecordIn(BaseModel):
    content: str


@app.get("/api/records/work/{uid}")
def get_work_records(uid: int, user: dict = Depends(_current_user)):
    uid = _self_uid(user, uid)
    return {"records": af.get_work_records(uid)}


@app.post("/api/records/work/{uid}")
def add_work_record(uid: int, body: WorkRecordIn, user: dict = Depends(_current_user)):
    uid = _self_uid(user, uid)
    return af.add_work_record(uid, body.content)


@app.delete("/api/records/work/{rid}")
def delete_work_record(rid: int, user: dict = Depends(_current_user)):
    """删除工作记录：员工删自己的；经理仅删本公司员工的。"""
    if user["role"] == "manager":
        owner = af.get_work_record_owner(rid)
        if not owner:
            return {"ok": False, "msg": "记录不存在"}
        if owner.get("company_id") != user.get("company_id"):
            raise HTTPException(status_code=403, detail="无权删除其他公司记录")
        return af.delete_work_record(rid, None)
    return af.delete_work_record(rid, user["id"])


def _read_text_bytes(data: bytes) -> str:
    """尽力把上传的文档字节解码成文本（UTF-8 → GBK → 兜底）。"""
    for enc in ("utf-8", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


@app.post("/api/records/work/{uid}/upload")
async def upload_work_record_file(uid: int, file: UploadFile = File(...), user: dict = Depends(_current_user)):
    """上传文档，解析文本内容存入工作记录。"""
    uid = _self_uid(user, uid)
    try:
        data = await _read_upload_bytes(file)
    except ValueError:
        return {"ok": False, "msg": f"文件过大（上限 {MAX_UPLOAD_BYTES // (1024*1024)}MB）"}
    text = _read_text_bytes(data).strip()
    if not text:
        return {"ok": False, "msg": "无法解析该文档，请上传文本类文件（.txt/.md/.log/.csv 等）"}
    return af.add_work_record(uid, f"[文档] {text[:2000]}")


@app.post("/api/records/work/{uid}/from-chats")
def import_work_records_from_chats(uid: int, user: dict = Depends(_current_user)):
    """把该用户最近发的聊天消息导入为工作记录。"""
    uid = _self_uid(user, uid)
    msgs = chat.get_user_sent_messages(uid, limit=30)
    if not msgs:
        return {"ok": False, "msg": "没有可导入的聊天记录"}
    for m in msgs:
        af.add_work_record(uid, f"[聊天记录] {m['content']}")
    return {"ok": True, "count": len(msgs)}


# ---- 个人能力知识库（让 Agent 读取电脑 → RAG）----
@app.post("/api/knowledge/{uid}/upload")
async def upload_ability_files(uid: int, files: list[UploadFile] = File(...), user: dict = Depends(_current_user)):
    """员工选择本地文件夹/文档上传，RAG 进个人能力知识库。"""
    uid = _self_uid(user, uid)
    texts = []
    for f in files:
        try:
            data = await _read_upload_bytes(f)
        except ValueError:
            return {"ok": False, "msg": f"文件过大（上限 {MAX_UPLOAD_BYTES // (1024*1024)}MB）"}
        text = _read_text_bytes(data).strip()
        if text:
            texts.append(text[:3000])
    if not texts:
        return {"ok": False, "msg": "没有可解析的文本内容"}
    n = ability_kb.add(uid, texts)
    # 读取文档后，用 LLM 判断真实工种，重新命名 agent
    rename_info = None
    agent = af.get_agent_by_user(uid)
    if agent:
        rename_info = af.rename_agent_by_ability(agent["id"])
    return {"ok": True, "count": n, "added": len(texts), "rename": rename_info}


@app.get("/api/knowledge/{uid}/stats")
def ability_kb_stats(uid: int, user: dict = Depends(_current_user)):
    uid = _self_uid(user, uid)
    return {"count": ability_kb.stats(uid)}


@app.get("/api/knowledge/{uid}/search")
def ability_kb_search(uid: int, q: str = "", user: dict = Depends(_current_user)):
    uid = _self_uid(user, uid)
    return {"hits": ability_kb.search(uid, q, top_k=3)}


# ---- 用户本地个人知识库 + DeepSeek RAG ----
class ProfileIn(BaseModel):
    info: str = ""
    habits: str = ""


class AgentChatIn(BaseModel):
    message: str
    user_id: int


@app.get("/api/profile/{uid}")
def get_profile(uid: int, user: dict = Depends(_current_user)):
    """读取用户画像（信息与习惯）"""
    uid = _self_uid(user, uid)
    return {"ok": True, "profile": personal_rag.get_profile(uid)}


@app.post("/api/profile/{uid}")
def set_profile(uid: int, body: ProfileIn, user: dict = Depends(_current_user)):
    """保存/更新用户画像（信息与习惯）"""
    uid = _self_uid(user, uid)
    return personal_rag.upsert_profile(uid, body.info, body.habits)


@app.post("/api/profile/{uid}/index")
def index_profile(uid: int, user: dict = Depends(_current_user)):
    """把画像 + 工作记录 + 聊天记录 + 能力库统一索引到本地知识库"""
    uid = _self_uid(user, uid)
    return personal_rag.index_user_sources(uid)


@app.post("/api/agent/chat")
def agent_chat(body: AgentChatIn, user: dict = Depends(_current_user)):
    """RAG 问答：DeepSeek 读取用户信息/习惯与检索片段后个性化作答"""
    return personal_rag.ask(user["id"], body.message)


# ---- 知识库②：任务条件 ----
class TaskConditionIn(BaseModel):
    company_id: int | None = None
    keywords: str
    conditions: str


@app.get("/api/conditions/{company_id}")
def get_task_conditions(company_id: int, user: dict = Depends(_current_user)):
    """任务条件库（仅本公司成员可见）"""
    if user.get("company_id") != company_id:
        raise HTTPException(status_code=403, detail="无权查看其他公司条件库")
    return {"conditions": af.get_task_conditions(company_id)}


@app.post("/api/conditions")
def add_task_condition(body: TaskConditionIn, user: dict = Depends(require_role("manager"))):
    """新增任务条件（仅本公司经理；company_id 以登录态为准）"""
    cid = body.company_id if body.company_id is not None else user.get("company_id")
    if cid != user.get("company_id"):
        raise HTTPException(status_code=403, detail="无权写入其他公司条件库")
    return af.add_task_condition(cid, body.keywords, body.conditions)


@app.delete("/api/conditions/{cid}")
def delete_task_condition(cid: int, user: dict = Depends(require_role("manager"))):
    """删除任务条件（仅本公司经理）"""
    conds = af.get_task_conditions(user.get("company_id"))
    if not any(c["id"] == cid for c in conds):
        raise HTTPException(status_code=403, detail="无权删除其他公司条件")
    return af.delete_task_condition(cid)


# ---- 通知 ----
@app.get("/api/notifications/{uid}")
def get_notifications(uid: int, user: dict = Depends(_current_user)):
    uid = _self_uid(user, uid)
    return {"notifications": af.get_notifications(uid)}


@app.post("/api/notifications/{uid}/read")
def read_notifications(uid: int, user: dict = Depends(_current_user)):
    uid = _self_uid(user, uid)
    return af.mark_notifications_read(uid)


# ---- 群聊 ----
class CreateGroupIn(BaseModel):
    name: str
    member_ids: list[int]


class AddMemberIn(BaseModel):
    user_id: int


@app.post("/api/chats/group")
def create_group(body: CreateGroupIn, user: dict = Depends(_current_user)):
    """几人一起建群（创建者自动计入成员）"""
    if not body.member_ids:
        return {"ok": False, "msg": "请至少选择一位成员"}
    mids = list(body.member_ids)
    if user["id"] not in mids:
        mids.append(user["id"])
    cid = chat.create_chat("group", body.name, tuple(mids))
    return {"ok": True, "chat_id": cid}


@app.get("/api/chats/{cid}/members")
def chat_members(cid: int, user: dict = Depends(_current_user)):
    """会话成员列表（仅成员可见）"""
    if not chat.is_chat_member(cid, user["id"]):
        raise HTTPException(status_code=403, detail="你不在该会话中")
    return {"members": chat.get_chat_members(cid), "chat": chat.get_chat_info(cid)}


@app.post("/api/chats/{cid}/members")
def add_member(cid: int, body: AddMemberIn, user: dict = Depends(require_role("manager"))):
    """经理强拉人进群"""
    return chat.add_chat_member(cid, body.user_id)


class GroupInviteIn(BaseModel):
    requester_id: int
    target_id: int


class RespondInviteIn(BaseModel):
    user_id: int
    approve: bool
    role: str


@app.post("/api/chats/{cid}/invite")
def create_group_invite(cid: int, body: GroupInviteIn, user: dict = Depends(_current_user)):
    """员工发起加群申请（需对方 + 经理双审）"""
    return chat.create_group_invite(cid, user["id"], body.target_id)


@app.get("/api/invites/target/{uid}")
def invites_for_target(uid: int, user: dict = Depends(_current_user)):
    """被加的人：待我审核的加群申请"""
    uid = _self_uid(user, uid)
    return {"invites": chat.get_invites_for_target(uid)}


@app.get("/api/invites/manager")
def invites_for_manager(user: dict = Depends(require_role("manager"))):
    """经理：待我审核的加群申请"""
    return {"invites": chat.get_pending_invites_for_manager()}


@app.post("/api/invites/{iid}/respond")
def respond_invite(iid: int, body: RespondInviteIn, user: dict = Depends(_current_user)):
    """对方 / 经理审核加群申请"""
    return chat.respond_group_invite(iid, user["id"], body.approve, user["role"])


@app.post("/api/submissions/image")
async def upload_submission_image(file: UploadFile = File(...), user: dict = Depends(_current_user)):
    """员工上传成果凭证照片，返回可访问的 URL"""
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    try:
        data = await _read_upload_bytes(file)
    except ValueError:
        return {"ok": False, "msg": f"文件过大（上限 {MAX_UPLOAD_BYTES // (1024*1024)}MB）"}
    filename = _safe_upload_filename(file.filename, ALLOWED_IMAGE_EXTS, ".jpg")
    path = os.path.join(config.UPLOAD_DIR, filename)
    with open(path, "wb") as f:
        f.write(data)
    return {"ok": True, "url": f"/uploads/{filename}"}


@app.post("/api/submissions/submit")
def submit_work(body: SubmitWorkIn, user: dict = Depends(_current_user)):
    """员工提交成果（可附照片凭证）"""
    agent = af.get_agent_by_user(user["id"])
    if not agent or agent["id"] != body.agent_id:
        return {"ok": False, "msg": "只能提交自己的工作"}
    return af.submit_work(body.task_id, body.agent_id, body.content, body.images)


@app.post("/api/submissions/{sid}/review")
def review_submission(sid: int, body: ReviewSubmissionIn, user: dict = Depends(require_role("manager"))):
    """审核提交（经理可选豁免绩效 / 手动改价）"""
    _require_company_submission(sid, user)
    return af.review_submission(sid, body.approve, body.exempt, body.custom_price)


# ---- 权责审核流水线（四阶段）----
class DesignateTechIn(BaseModel):
    user_id: int


class TechVerifyIn(BaseModel):
    user_id: int
    approve: bool


class ManagerVerifyIn(BaseModel):
    approve: bool
    custom_price: float = None


@app.post("/api/submissions/{sid}/agent-check")
def agent_check(sid: int, user: dict = Depends(_current_user)):
    """阶段①：员工 agent 自检（仅提交者本人）"""
    sub = af.get_submission(sid)
    if not sub:
        raise HTTPException(status_code=404, detail="提交不存在")
    agent = af.get_agent_by_user(user["id"])
    if not agent or sub.get("agent_id") != agent["id"]:
        raise HTTPException(status_code=403, detail="只能自检自己的提交")
    return af.agent_check_submission(sid)


@app.post("/api/submissions/{sid}/manager-test")
def manager_test(sid: int, user: dict = Depends(require_role("manager"))):
    """阶段②：经理 agent 跑小项目测试"""
    _require_company_submission(sid, user)
    return af.manager_test_submission(sid)


@app.post("/api/submissions/{sid}/manager-verify")
def manager_verify(sid: int, body: ManagerVerifyIn, user: dict = Depends(require_role("manager"))):
    """阶段③：经理核验（可改价）"""
    _require_company_submission(sid, user)
    return af.manager_verify_submission(sid, body.approve, body.custom_price)


@app.post("/api/submissions/{sid}/designate-tech")
def designate_tech(sid: int, body: DesignateTechIn, user: dict = Depends(require_role("manager"))):
    """经理指定技术人员（仅本公司）"""
    _require_company_submission(sid, user)
    tech = auth.get_user_by_id(body.user_id)
    if not tech or tech.get("company_id") != user.get("company_id"):
        raise HTTPException(status_code=403, detail="只能指定本公司技术员")
    return af.designate_tech_reviewer(sid, body.user_id)


@app.post("/api/submissions/{sid}/tech-verify")
def tech_verify(sid: int, body: TechVerifyIn, user: dict = Depends(_current_user)):
    """阶段④：技术人员验证（仅被指定的技术员或本公司经理）"""
    sub = af.get_submission(sid)
    if not sub:
        raise HTTPException(status_code=404, detail="提交不存在")
    if user["role"] != "manager":
        if not sub.get("tech_reviewer") or sub["tech_reviewer"] != user["id"]:
            raise HTTPException(status_code=403, detail="你不是被指定的技术员")
    else:
        _require_company_submission(sid, user)
    return af.tech_verify_submission(sid, user["id"], body.approve)


# ---- 工资发放方式 ----
class PayModeIn(BaseModel):
    pay_mode: str


@app.get("/api/company/{cid}/pay-mode")
def get_pay_mode(cid: int, user: dict = Depends(_current_user)):
    """查询公司工资发放方式（仅本公司成员）"""
    if user.get("company_id") != cid:
        raise HTTPException(status_code=403, detail="无权查看其他公司")
    return {"pay_mode": company.get_pay_mode(cid)}


@app.post("/api/company/{cid}/pay-mode")
def set_pay_mode(cid: int, body: PayModeIn, user: dict = Depends(require_role("manager"))):
    if user.get("company_id") != cid:
        raise HTTPException(status_code=403, detail="无权操作其他公司")
    return company.set_pay_mode(cid, body.pay_mode)


@app.post("/api/payouts/pay-all")
def pay_all_payouts(user: dict = Depends(require_role("manager"))):
    """每月固定时间：一次性发放本公司所有待打款工资"""
    return af.pay_all_payouts(user.get("company_id"))


@app.post("/api/salary/{uid}/set")
def set_salary(uid: int, body: SetSalaryIn, user: dict = Depends(require_role("manager"))):
    """更新员工工资与豁免标记（仅本公司员工）"""
    target = auth.get_user_by_id(uid)
    if not target:
        return {"ok": False, "msg": "用户不存在"}
    if target.get("company_id") != user.get("company_id"):
        raise HTTPException(status_code=403, detail="无权操作其他公司员工")
    return af.update_salary(uid, body.base_salary, body.exempt)


# ---- 查询接口：员工「我的任务 / 我的工资」 + 经理「工作台 / 审核」 ----
@app.get("/api/agents/user/{uid}")
def get_agent_by_user(uid: int, user: dict = Depends(_current_user)):
    """按 user_id 查员工专属 Agent（不存在返回 None）"""
    uid = _self_uid(user, uid)
    return af.get_agent_by_user(uid)


@app.get("/api/tasks/agent/{agent_id}")
def get_agent_tasks(agent_id: int, user: dict = Depends(_current_user)):
    """员工「我的任务」：派给该 agent 的任务 + 提交反馈。

    员工只能看自己的 Agent；经理可看本公司员工的 Agent。
    """
    agent = af.get_agent(agent_id)
    if not agent:
        return {"tasks": []}
    if user["role"] != "manager" and agent.get("user_id") != user["id"]:
        raise HTTPException(status_code=403, detail="只能查看自己的任务")
    if user["role"] == "manager":
        owner = auth.get_user_by_id(agent.get("user_id"))
        if not owner or owner.get("company_id") != user.get("company_id"):
            raise HTTPException(status_code=403, detail="只能查看本公司员工的任务")
    return {"tasks": af.get_agent_tasks(agent_id)}


@app.get("/api/salary/{uid}")
def get_salary(uid: int, user: dict = Depends(_current_user)):
    """员工「我的工资」：基础工资 + 豁免标记"""
    uid = _self_uid(user, uid)
    return af.get_salary(uid)


@app.get("/api/submissions/pending")
def get_pending_submissions(user: dict = Depends(require_role("manager"))):
    """经理「审核」：待审核的提交列表（本公司）"""
    return {"submissions": af.get_pending_submissions(user.get("company_id"))}


@app.get("/api/dashboard/stats")
def dashboard_stats(user: dict = Depends(require_role("manager"))):
    """经理「工作台」：待办与团队概览（本公司）"""
    cid = user.get("company_id")
    return {
        "pending_classify": len(af.get_pending_classification(cid)),
        "pending_submissions": len(af.get_pending_submissions(cid)),
        "team_agents": af.count_agents(cid),
    }


# ---- 工资结算 / 打款 ----
@app.get("/api/payouts")
def get_payouts(user: dict = Depends(require_role("manager"))):
    """经理「结算」：本公司结算记录（含待打款 / 已打款）"""
    cid = user.get("company_id")
    return {"payouts": af.get_payouts(company_id=cid), "stats": af.get_payout_stats(cid)}


@app.post("/api/payouts/{pid}/pay")
def pay_payout(pid: int, user: dict = Depends(require_role("manager"))):
    """经理打款：把某笔待打款置为已打款（仅本公司）"""
    payout = af.get_payout(pid)
    if not payout:
        raise HTTPException(status_code=404, detail="结算记录不存在")
    owner = auth.get_user_by_id(payout.get("user_id"))
    if not owner or owner.get("company_id") != user.get("company_id"):
        raise HTTPException(status_code=403, detail="无权操作其他公司打款")
    return af.pay_payout(pid)


@app.get("/api/payouts/user/{uid}")
def get_user_payouts(uid: int, user: dict = Depends(_current_user)):
    """员工「到账记录」"""
    uid = _self_uid(user, uid)
    return {"payouts": af.get_user_payouts(uid)}


# ---- SaaS 套餐 / 订单 / 订阅 ----
class CreateOrderIn(BaseModel):
    user_id: int
    plan_id: int


@app.get("/api/plans")
def get_plans():
    """套餐列表"""
    return {"plans": payment.get_plans()}


@app.post("/api/orders")
def create_order(body: CreateOrderIn, user: dict = Depends(_current_user)):
    """创建订单（待支付）"""
    return payment.create_order(user["id"], body.plan_id)


@app.post("/api/orders/{order_no}/pay")
def pay_order(order_no: str, user: dict = Depends(_current_user)):
    """模拟支付成功（真实支付网关接入后替换此逻辑）"""
    order = payment.get_order_by_no(order_no)
    if order and order["user_id"] != user["id"] and user["role"] != "manager":
        return {"ok": False, "msg": "只能支付自己的订单"}
    return payment.pay_order(order_no)


@app.get("/api/subscriptions/{uid}")
def get_subscription(uid: int, user: dict = Depends(_current_user)):
    """某用户的当前订阅状态"""
    uid = _self_uid(user, uid)
    return payment.get_subscription(uid)


if __name__ == "__main__":
    import os
    import uvicorn
    # 默认本机访问；内网部署设 HOST=0.0.0.0 即可让内网其他电脑访问
    host = os.environ.get("HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=8000)
