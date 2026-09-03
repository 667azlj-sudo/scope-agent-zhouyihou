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
import chat
import company
import graphrag
import knowledge
import llm
import memory
import sms
import payment
import agent_framework as af
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
def get_chat_messages(cid: int):
    """获取会话消息"""
    return {"messages": chat.get_messages(cid)}


@app.post("/api/chats/{cid}/read")
def mark_chat_read(cid: int, body: MarkReadIn):
    """标记会话已读（消除红点）"""
    user = auth.get_user_by_token(body.token)
    if not user:
        return {"ok": False, "msg": "未登录或 token 无效"}
    chat.mark_read(cid, user["id"])
    return {"ok": True, "msg": "已读"}


@app.post("/api/config/llm")
def config_llm(api_key: str = Form("")):
    """用户提交 DeepSeek API key，切换到云端模式并持久化（重启仍生效）"""
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
    phone = _normalize_phone(body.phone) if body.phone else None
    if phone:
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
    import uuid
    os.makedirs("uploads", exist_ok=True)
    ext = os.path.splitext(file.filename or "")[1] or ".jpg"
    filename = f"chat_{uuid.uuid4().hex[:12]}{ext}"
    path = os.path.join("uploads", filename)
    with open(path, "wb") as f:
        f.write(await file.read())
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


class SetSalaryIn(BaseModel):
    base_salary: float
    exempt: bool


@app.post("/api/agents/{user_id}/create")
def create_agent(user_id: int, body: CreateAgentIn):
    """为员工建立 Agent（user_id 唯一）"""
    agent = af.create_agent(user_id, body.role_type, body.name, body.config)
    return {"agent_id": agent["id"]}


@app.post("/api/tasks/split")
def split_task(body: SplitTaskIn):
    """让 LLM 把任务拆成子任务并入库"""
    subtasks = af.split_task(body.title, body.detail, body.manager_agent_id)
    return {"subtasks": subtasks}


@app.get("/api/tasks/pending-classify")
def pending_classify():
    """经理看待确认分级（pending_classify）的子任务列表"""
    return {"tasks": af.get_pending_classification()}


@app.post("/api/tasks/{tid}/classify")
def classify(tid: int, body: ClassifyTaskIn):
    """经理选择分级：internal=机密→内部分配 / outsource=一般→外包候选"""
    return af.manager_choose(tid, body.choice)


@app.post("/api/tasks/distribute")
def distribute_task(body: AssignTaskIn):
    """经理 agent 把内部任务分发给某个员工 agent（distributed）"""
    return af.distribute_task(body.agent_id, body.task_id)


@app.post("/api/tasks/estimate")
def estimate_task(body: EstimateTaskIn):
    """员工 agent 审核任务并报价（结合本地记录给工时+工资）"""
    return af.estimate_task(body.agent_id, body.task_id)


@app.post("/api/tasks/{tid}/review-estimate")
def review_estimate(tid: int, body: ReviewEstimateIn):
    """经理 agent 审核报价：通过→正式派发 / 打回→重新报价"""
    return af.review_estimate(tid, body.approve)


@app.get("/api/tasks/internal")
def internal_tasks():
    """经理看待分发的内部任务"""
    return {"tasks": af.get_internal_tasks()}


@app.get("/api/tasks/estimated")
def estimated_tasks():
    """经理看待审核报价的任务"""
    return {"tasks": af.get_estimated_tasks()}


class PublishHallIn(BaseModel):
    candidate_ids: list[int]


class ClaimTaskIn(BaseModel):
    user_id: int


@app.get("/api/tasks/unmatched")
def unmatched_tasks():
    """经理端：无人接手的任务"""
    return {"tasks": af.get_unmatched_tasks()}


@app.post("/api/tasks/{tid}/publish-hall")
def publish_hall(tid: int, body: PublishHallIn):
    """经理选候选人后发布到任务大厅"""
    return af.publish_to_hall(tid, body.candidate_ids)


@app.get("/api/hall/{uid}")
def hall_tasks(uid: int):
    """任务大厅：该用户作为候选人的待接取任务"""
    return {"tasks": af.get_hall_tasks(uid)}


@app.post("/api/hall/{tid}/claim")
def claim_task(tid: int, body: ClaimTaskIn):
    """候选人接取大厅任务"""
    return af.claim_task(tid, body.user_id)


class AcceptOutsourceIn(BaseModel):
    user_id: int


@app.get("/api/outsource")
def outsource_tasks():
    """外包大厅：所有待接取的外包任务（跨公司）"""
    return {"tasks": af.get_outsource_tasks()}


@app.post("/api/outsource/{tid}/accept")
def accept_outsource(tid: int, body: AcceptOutsourceIn):
    """其他公司的人接取外包任务"""
    return af.accept_outsource(tid, body.user_id)


@app.get("/api/agents")
def list_agents():
    """所有 Agent（附用户名/岗位/公司），经理分发时选择"""
    return {"agents": af.list_agents()}


@app.get("/api/users")
def list_users():
    """所有用户（建群/拉人时选择成员用）"""
    return {"users": [
        {"id": u["id"], "name": u["name"], "role": u["role"],
         "position": u.get("position"), "company_id": u.get("company_id")}
        for u in auth.get_all_users()
    ]}


@app.get("/api/companies")
def list_companies():
    """公司列表（注册时可选）"""
    return {"companies": company.list_companies()}


@app.get("/api/companies/by-code")
def company_by_code(code: str):
    """按邀请码查公司"""
    return company.get_company_by_code(code)


@app.get("/api/companies/{cid}")
def company_detail(cid: int):
    """公司详情：基本信息 + 邀请码 + 成员列表"""
    comp = company.get_company(cid)
    if not comp:
        return {"ok": False, "msg": "公司不存在"}
    return {"ok": True, "company": comp, "members": company.get_company_members(cid)}


@app.get("/api/records/{uid}")
def get_records(uid: int):
    """员工本地记录（个人档案/技能/历史绩效）"""
    return af.get_user_records(uid)


@app.post("/api/records/{uid}")
def save_records(uid: int, body: SaveRecordIn):
    """保存员工本地记录"""
    return af.save_user_records(uid, body.content)


# ---- 知识库①：工作记录 ----
class WorkRecordIn(BaseModel):
    content: str


@app.get("/api/records/work/{uid}")
def get_work_records(uid: int):
    return {"records": af.get_work_records(uid)}


@app.post("/api/records/work/{uid}")
def add_work_record(uid: int, body: WorkRecordIn):
    return af.add_work_record(uid, body.content)


@app.delete("/api/records/work/{rid}")
def delete_work_record(rid: int):
    return af.delete_work_record(rid)


def _read_text_bytes(data: bytes) -> str:
    """尽力把上传的文档字节解码成文本（UTF-8 → GBK → 兜底）。"""
    for enc in ("utf-8", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


@app.post("/api/records/work/{uid}/upload")
async def upload_work_record_file(uid: int, file: UploadFile = File(...)):
    """上传文档，解析文本内容存入工作记录。"""
    data = await file.read()
    text = _read_text_bytes(data).strip()
    if not text:
        return {"ok": False, "msg": "无法解析该文档，请上传文本类文件（.txt/.md/.log/.csv 等）"}
    return af.add_work_record(uid, f"[文档] {text[:2000]}")


@app.post("/api/records/work/{uid}/from-chats")
def import_work_records_from_chats(uid: int):
    """把该用户最近发的聊天消息导入为工作记录。"""
    msgs = chat.get_user_sent_messages(uid, limit=30)
    if not msgs:
        return {"ok": False, "msg": "没有可导入的聊天记录"}
    for m in msgs:
        af.add_work_record(uid, f"[聊天记录] {m['content']}")
    return {"ok": True, "count": len(msgs)}


# ---- 知识库②：任务条件 ----
class TaskConditionIn(BaseModel):
    company_id: int | None = None
    keywords: str
    conditions: str


@app.get("/api/conditions/{company_id}")
def get_task_conditions(company_id: int):
    return {"conditions": af.get_task_conditions(company_id)}


@app.post("/api/conditions")
def add_task_condition(body: TaskConditionIn):
    return af.add_task_condition(body.company_id, body.keywords, body.conditions)


@app.delete("/api/conditions/{cid}")
def delete_task_condition(cid: int):
    return af.delete_task_condition(cid)


# ---- 通知 ----
@app.get("/api/notifications/{uid}")
def get_notifications(uid: int):
    return {"notifications": af.get_notifications(uid)}


@app.post("/api/notifications/{uid}/read")
def read_notifications(uid: int):
    return af.mark_notifications_read(uid)


# ---- 群聊 ----
class CreateGroupIn(BaseModel):
    name: str
    member_ids: list[int]


class AddMemberIn(BaseModel):
    user_id: int


@app.post("/api/chats/group")
def create_group(body: CreateGroupIn):
    """几人一起建群（member_ids 需包含创建者）"""
    if not body.member_ids:
        return {"ok": False, "msg": "请至少选择一位成员"}
    cid = chat.create_chat("group", body.name, tuple(body.member_ids))
    return {"ok": True, "chat_id": cid}


@app.get("/api/chats/{cid}/members")
def chat_members(cid: int):
    return {"members": chat.get_chat_members(cid), "chat": chat.get_chat_info(cid)}


@app.post("/api/chats/{cid}/members")
def add_member(cid: int, body: AddMemberIn):
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
def create_group_invite(cid: int, body: GroupInviteIn):
    """员工发起加群申请（需对方 + 经理双审）"""
    return chat.create_group_invite(cid, body.requester_id, body.target_id)


@app.get("/api/invites/target/{uid}")
def invites_for_target(uid: int):
    """被加的人：待我审核的加群申请"""
    return {"invites": chat.get_invites_for_target(uid)}


@app.get("/api/invites/manager")
def invites_for_manager():
    """经理：待我审核的加群申请"""
    return {"invites": chat.get_pending_invites_for_manager()}


@app.post("/api/invites/{iid}/respond")
def respond_invite(iid: int, body: RespondInviteIn):
    """对方 / 经理审核加群申请"""
    return chat.respond_group_invite(iid, body.user_id, body.approve, body.role)


@app.post("/api/submissions/image")
async def upload_submission_image(file: UploadFile = File(...)):
    """员工上传成果凭证照片，返回可访问的 URL"""
    import uuid
    os.makedirs("uploads", exist_ok=True)
    ext = os.path.splitext(file.filename or "")[1] or ".jpg"
    filename = f"sub_{uuid.uuid4().hex[:12]}{ext}"
    path = os.path.join("uploads", filename)
    with open(path, "wb") as f:
        f.write(await file.read())
    return {"ok": True, "url": f"/uploads/{filename}"}


@app.post("/api/submissions/submit")
def submit_work(body: SubmitWorkIn):
    """员工提交成果（可附照片凭证）"""
    return af.submit_work(body.task_id, body.agent_id, body.content, body.images)


@app.post("/api/submissions/{sid}/review")
def review_submission(sid: int, body: ReviewSubmissionIn):
    """审核提交（经理可选豁免绩效）"""
    return af.review_submission(sid, body.approve, body.exempt)


@app.post("/api/salary/{uid}/set")
def set_salary(uid: int, body: SetSalaryIn):
    """更新员工工资与豁免标记"""
    return af.update_salary(uid, body.base_salary, body.exempt)


# ---- 查询接口：员工「我的任务 / 我的工资」 + 经理「工作台 / 审核」 ----
@app.get("/api/agents/user/{uid}")
def get_agent_by_user(uid: int):
    """按 user_id 查员工专属 Agent（不存在返回 None）"""
    return af.get_agent_by_user(uid)


@app.get("/api/tasks/agent/{agent_id}")
def get_agent_tasks(agent_id: int):
    """员工「我的任务」：派给该 agent 的任务 + 提交反馈"""
    return {"tasks": af.get_agent_tasks(agent_id)}


@app.get("/api/salary/{uid}")
def get_salary(uid: int):
    """员工「我的工资」：基础工资 + 豁免标记"""
    return af.get_salary(uid)


@app.get("/api/submissions/pending")
def get_pending_submissions():
    """经理「审核」：待审核的提交列表"""
    return {"submissions": af.get_pending_submissions()}


@app.get("/api/dashboard/stats")
def dashboard_stats():
    """经理「工作台」：待办与团队概览"""
    return {
        "pending_classify": len(af.get_pending_classification()),
        "pending_submissions": len(af.get_pending_submissions()),
        "team_agents": af.count_agents(),
    }


# ---- 工资结算 / 打款 ----
@app.get("/api/payouts")
def get_payouts():
    """经理「结算」：全部结算记录（含待打款 / 已打款）"""
    return {"payouts": af.get_payouts(), "stats": af.get_payout_stats()}


@app.post("/api/payouts/{pid}/pay")
def pay_payout(pid: int):
    """经理打款：把某笔待打款置为已打款"""
    return af.pay_payout(pid)


@app.get("/api/payouts/user/{uid}")
def get_user_payouts(uid: int):
    """员工「到账记录」"""
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
def create_order(body: CreateOrderIn):
    """创建订单（待支付）"""
    return payment.create_order(body.user_id, body.plan_id)


@app.post("/api/orders/{order_no}/pay")
def pay_order(order_no: str):
    """模拟支付成功（真实支付网关接入后替换此逻辑）"""
    return payment.pay_order(order_no)


@app.get("/api/subscriptions/{uid}")
def get_subscription(uid: int):
    """某用户的当前订阅状态"""
    return payment.get_subscription(uid)


if __name__ == "__main__":
    import os
    import uvicorn
    # 默认本机访问；内网部署设 HOST=0.0.0.0 即可让内网其他电脑访问
    host = os.environ.get("HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=8000)
