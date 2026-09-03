# -*- coding: utf-8 -*-
"""
agent_framework.py —— 多 Agent 协作框架核心

设计依据见 multiagent_design.md。
表名约定：所有任务相关表一律命名为 agent_tasks（避免与 db.py 中已有的 tasks 表冲突）。

表：
  agents          —— 员工 Agent（每员工一个，user_id 唯一）
  agent_tasks     —— 任务 / 子任务
  submissions     —— 员工提交的成果
  agent_messages  —— Agent 间的消息
  salaries        —— 员工基础工资与豁免标记
"""
import json
import re
import sqlite3

DB_PATH = "scope_agent.db"

ROLE_TYPES = ("employee", "functional", "manager")

# Agent 可用工具（manager 额外多一个 review）
BASE_TOOLS = ["query_db", "message_agent", "get_task", "submit_work"]


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row   # 让查询结果能按列名访问
    return conn


def init_agent_db():
    """建 5 张表：agents / agent_tasks / submissions / agent_messages / salaries"""
    conn = get_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS agents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL UNIQUE,
        role_type TEXT NOT NULL,
        name TEXT NOT NULL,
        config TEXT DEFAULT '{}',
        created_at TEXT DEFAULT (datetime('now', 'localtime'))
    );

    CREATE TABLE IF NOT EXISTS agent_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        detail TEXT DEFAULT '',
        difficulty REAL DEFAULT 0.5,
        status TEXT DEFAULT 'pending',
        assignee_role TEXT DEFAULT '',
        assignee_agent INTEGER,
        manager_agent INTEGER,
        classification TEXT DEFAULT '一般',
        created_at TEXT DEFAULT (datetime('now', 'localtime'))
    );

    CREATE TABLE IF NOT EXISTS submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER NOT NULL,
        agent_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        price REAL DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now', 'localtime')),
        FOREIGN KEY (task_id) REFERENCES agent_tasks(id)
    );

    CREATE TABLE IF NOT EXISTS agent_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_agent INTEGER NOT NULL,
        to_agent INTEGER NOT NULL,
        content TEXT NOT NULL,
        priority INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now', 'localtime'))
    );

    CREATE TABLE IF NOT EXISTS salaries (
        user_id INTEGER PRIMARY KEY,
        base_salary REAL DEFAULT 0,
        exempt INTEGER DEFAULT 0,
        updated_at TEXT DEFAULT (datetime('now', 'localtime'))
    );

    CREATE TABLE IF NOT EXISTS payouts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        submission_id INTEGER NOT NULL UNIQUE,
        user_id INTEGER NOT NULL,
        agent_id INTEGER,
        amount REAL DEFAULT 0,
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT (datetime('now', 'localtime')),
        paid_at TEXT
    );

    CREATE TABLE IF NOT EXISTS user_records (
        user_id INTEGER PRIMARY KEY,
        content TEXT DEFAULT '',
        updated_at TEXT DEFAULT (datetime('now', 'localtime'))
    );

    CREATE TABLE IF NOT EXISTS work_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now', 'localtime'))
    );

    CREATE TABLE IF NOT EXISTS task_conditions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER,
        keywords TEXT DEFAULT '',
        conditions TEXT DEFAULT '',
        created_at TEXT DEFAULT (datetime('now', 'localtime'))
    );

    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        task_id INTEGER,
        is_read INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now', 'localtime'))
    );
    """)
    conn.commit()
    # 迁移：agent_tasks 增加报价相关列
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(agent_tasks)").fetchall()]
    for col, typ in [("estimated_hours", "REAL"), ("estimated_wage", "REAL"),
                     ("estimate_reason", "TEXT"), ("agreed_wage", "REAL"),
                     ("suitability", "TEXT"), ("suitability_reason", "TEXT"),
                     ("conditions", "TEXT"), ("needs_conditions", "INTEGER"),
                     ("candidates", "TEXT"), ("outsource_accepter", "INTEGER"),
                     ("outsource_accepter_company", "INTEGER")]:
        if col not in cols:
            conn.execute(f"ALTER TABLE agent_tasks ADD COLUMN {col} {typ}")
    # 迁移：submissions 增加 images 列（照片凭证）
    scols = [r["name"] for r in conn.execute("PRAGMA table_info(submissions)").fetchall()]
    if "images" not in scols:
        conn.execute("ALTER TABLE submissions ADD COLUMN images TEXT DEFAULT '[]'")
    conn.commit()
    conn.close()
    # 迁移：旧表没有 classification 列的话，ALTER TABLE 补上
    _migrate_agent_tasks_classification()


def _migrate_agent_tasks_classification():
    """老数据库的 agent_tasks 表可能没有 classification 列，补上（TEXT 默认 '一般'）。"""
    conn = get_conn()
    try:
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(agent_tasks)").fetchall()]
        if "classification" not in cols:
            conn.execute(
                "ALTER TABLE agent_tasks ADD COLUMN classification TEXT DEFAULT '一般'"
            )
            conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Agent 基础
# ---------------------------------------------------------------------------
def get_agent(agent_id):
    """按 id 查 agent，返回 dict 或 None"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_agent_by_user(user_id):
    """按 user_id 查 agent（每员工一个），返回 dict 或 None"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM agents WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def rename_agent_by_ability(agent_id):
    """读取该员工的能力知识库，用 LLM 判断真实工种，重新命名 Agent（如「张三 · 后端开发」）。"""
    agent = get_agent(agent_id)
    if not agent:
        return {"ok": False, "msg": "Agent 不存在"}
    try:
        import ability_kb
        records = ability_kb.load_records(agent["user_id"])
    except Exception:  # noqa: BLE001
        records = []
    if not records:
        return {"ok": False, "msg": "能力知识库为空，无法命名"}

    sample = "\n".join(t[:300] for t, _ in records[:10])
    specialty = "员工"
    try:
        from llm import chat as llm_chat
        system = ("你是岗位识别助手。根据员工的能力知识库内容，判断员工最擅长/真实从事的工种，"
                  "返回一个简短的工种名（如：后端开发、ToB销售、UI设计师），只返回工种名，不要多余文字。")
        resp = llm_chat([{"role": "system", "content": system},
                         {"role": "user", "content": sample}])
        name = (getattr(resp, "content", None) or "").strip()
        if name:
            specialty = name[:20]
    except Exception as e:  # noqa: BLE001
        print(f"[rename] LLM 命名失败：{e}")

    conn = get_conn()
    urow = conn.execute("SELECT name FROM users WHERE id=?", (agent["user_id"],)).fetchone()
    user_name = dict(urow)["name"] if urow else "员工"
    new_name = f"{user_name} · {specialty}"
    conn.execute("UPDATE agents SET name=? WHERE id=?", (new_name, agent_id))
    conn.commit()
    conn.close()
    return {"ok": True, "name": new_name, "specialty": specialty}


def create_agent(user_id, role_type, name, config=None):
    """为一个员工建立 Agent（user_id 唯一）。

    role_type 必须是 employee / functional / manager。
    config 为 dict，序列化成 JSON 存库。返回新建的 agent dict。
    """
    if role_type not in ROLE_TYPES:
        raise ValueError("role_type 必须是 employee/functional/manager")
    cfg = config or {}
    if not isinstance(cfg, dict):
        raise ValueError("config 必须是 dict")
    conn = get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO agents (user_id, role_type, name, config) VALUES (?,?,?,?)",
            (user_id, role_type, name, json.dumps(cfg, ensure_ascii=False)),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise ValueError(f"用户 {user_id} 已有员工Agent")
    aid = cur.lastrowid
    conn.close()
    return {"id": aid, "user_id": user_id, "role_type": role_type,
            "name": name, "config": cfg}


def agent_tools(agent_id):
    """返回该 agent 的工具列表。

    所有 agent 都有：query_db / message_agent / get_task / submit_work；
    只有 manager 多一个 review。
    """
    agent = get_agent(agent_id)
    if not agent:
        return []
    tools = list(BASE_TOOLS)
    if agent["role_type"] == "manager":
        tools.append("review")
    return tools


# ---------------------------------------------------------------------------
# 任务流
# ---------------------------------------------------------------------------
def _extract_json(text):
    """从 LLM 返回文本里提取 JSON（兼容 ```json 围栏 / 多行文本）。"""
    text = (text or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    for start, end in (("[", "]"), ("{", "}")):
        s = text.find(start)
        e = text.rfind(end)
        if s != -1 and e != -1 and e > s:
            try:
                return json.loads(text[s:e + 1])
            except Exception:
                continue
    return None


def split_task(title, detail, manager_agent_id=None):
    """让 LLM 把任务拆成子任务列表。

    返回 [{title, detail, assignee_role, classification}, ...]，并把每个子任务写进
    agent_tasks（status=pending_classify，待经理确认分级后再分配）。
    """
    from llm import chat as llm_chat

    system = (
        "你是一个任务拆解助手。把用户给定的任务拆成 3~6 个可执行的子任务。"
        "每个子任务包含字段 title(标题)、detail(具体要求)、assignee_role(负责角色，"
        "只能是 employee/functional/manager)、classification(分级，取值只能是"
        "「机密」或「一般」：涉及公司核心秘密、敏感数据或不可外泄的内容判定为「机密」，"
        "否则普通可外包的内容判定为「一般」)。只返回 JSON 数组，不要输出多余文字。"
    )
    user = f"任务标题：{title}\n任务详情：{detail}"
    resp = llm_chat([{"role": "system", "content": system},
                     {"role": "user", "content": user}])
    data = _extract_json(getattr(resp, "content", None))
    if not isinstance(data, list):
        raise ValueError("LLM 任务拆分结果不是一个数组")

    conn = get_conn()
    try:
        created = []
        for item in data:
            sub_title = str(item.get("title", "")).strip()
            sub_detail = str(item.get("detail", "")).strip()
            assignee_role = item.get("assignee_role", "employee")
            if assignee_role not in ROLE_TYPES:
                assignee_role = "employee"
            classification = item.get("classification", "一般")
            if classification not in ("机密", "一般"):
                classification = "一般"
            cur = conn.execute(
                "INSERT INTO agent_tasks (title, detail, assignee_role, status, "
                "manager_agent, classification) VALUES (?,?,?,?,?,?)",
                (sub_title, sub_detail, assignee_role, "pending_classify",
                 manager_agent_id, classification),
            )
            created.append({
                "id": cur.lastrowid,
                "title": sub_title,
                "detail": sub_detail,
                "assignee_role": assignee_role,
                "classification": classification,
                "status": "pending_classify",
                "manager_agent": manager_agent_id,
            })
        conn.commit()
        return created
    finally:
        conn.close()


def get_pending_classification():
    """查所有待经理确认分级（status=pending_classify）的子任务，含分类信息。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM agent_tasks WHERE status='pending_classify' ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def manager_choose(task_id, choice):
    """经理对某个待确认子任务做分级选择。

    choice='internal'：机密 → 内部分配；随后查知识库判断是否有人能接手，无人则标 unmatched。
    choice='outsource'：一般 → 外包候选。
    """
    if choice not in ("internal", "outsource"):
        return {"ok": False, "msg": "choice 只能是 internal 或 outsource"}
    conn = get_conn()
    task = conn.execute("SELECT * FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
    if not task:
        conn.close()
        return {"ok": False, "msg": "任务不存在"}
    if task["status"] != "pending_classify":
        conn.close()
        return {"ok": False, "msg": "任务不是待确认分级状态，不能选择"}
    new_status = "internal" if choice == "internal" else "outsource"
    conn.execute("UPDATE agent_tasks SET status=? WHERE id=?", (new_status, task_id))
    conn.commit()
    conn.close()

    resp = {"ok": True, "task_id": task_id, "choice": choice, "status": new_status,
            "msg": "已内部分配（机密）" if choice == "internal" else "已列为外包候选（一般）"}

    # 内部任务：查知识库判断是否有人能接手，无人则标记 unmatched
    if choice == "internal":
        det = detect_unmatched(task_id)
        resp["unmatched"] = det.get("unmatched", False)
        resp["detect_reason"] = det.get("reason", "")
        if det.get("unmatched"):
            _c = get_conn()
            _c.execute("UPDATE agent_tasks SET status='unmatched' WHERE id=?", (task_id,))
            _c.commit()
            _c.close()
            resp["status"] = "unmatched"
            resp["msg"] = "无人接手，请选择候选人"
    return resp


def _task_company_id(task):
    """通过任务挂的经理 agent 找到公司 id。"""
    conn = get_conn()
    mid = task.get("manager_agent")
    row = None
    if mid:
        row = conn.execute(
            "SELECT u.company_id FROM agents a JOIN users u ON u.id=a.user_id WHERE a.id=?",
            (mid,)).fetchone()
    conn.close()
    return dict(row)["company_id"] if row and row["company_id"] else None


def _company_employees(company_id):
    """公司内所有员工 agent（含各自工作记录 + 本地记录），供适配判断。"""
    if not company_id:
        return []
    conn = get_conn()
    rows = conn.execute(
        "SELECT u.id AS user_id, u.name, a.id AS agent_id FROM users u "
        "JOIN agents a ON a.user_id=u.id WHERE u.company_id=? AND u.role='employee'",
        (company_id,)).fetchall()
    conn.close()
    out = []
    for r in rows:
        r = dict(r)
        profile = get_user_records(r["user_id"])["content"]
        works = "；".join(x["content"] for x in get_work_records(r["user_id"]))
        out.append({"user_id": r["user_id"], "agent_id": r["agent_id"],
                    "name": r["name"], "records": f"{profile} {works}".strip()})
    return out


def detect_unmatched(task_id):
    """查知识库判断是否有员工适合接手该任务；无人则返回 unmatched=True。"""
    conn = get_conn()
    task = conn.execute("SELECT * FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()
    if not task:
        return {"ok": False, "msg": "任务不存在"}
    task = dict(task)
    employees = _company_employees(_task_company_id(task))
    if not employees:
        return {"ok": True, "unmatched": True, "reason": "公司暂无员工记录可匹配"}

    text = f"{task['title']} {task.get('detail') or ''}"
    try:
        from llm import chat as llm_chat
        emp_text = "\n".join(f"- {e['name']}：{e['records'] or '（无记录）'}" for e in employees)
        system = ("你是任务适配判断助手。根据任务要求和各员工的工作记录，判断是否有员工适合接手该任务。"
                  "只返回 JSON：{\"matched\": true 或 false, \"reason\": \"一句话\"}，不要输出多余文字。")
        resp = llm_chat([{"role": "system", "content": system},
                         {"role": "user", "content": f"任务：{text}\n员工记录：\n{emp_text}"}])
        data = _extract_json(getattr(resp, "content", None))
        if isinstance(data, dict) and "matched" in data:
            return {"ok": True, "unmatched": not bool(data["matched"]),
                    "reason": str(data.get("reason", ""))}
    except Exception as e:  # noqa: BLE001
        print(f"[detect] LLM 适配判断失败，走关键词兜底：{e}")
    # 兜底：关键词命中任一员工记录即视为有人能接手
    try:
        import jieba
        kws = [w for w in jieba.lcut(text) if len(w.strip()) >= 2]
    except Exception:  # noqa: BLE001
        kws = text.split()
    for e in employees:
        if e["records"] and any(k in e["records"] for k in kws):
            return {"ok": True, "unmatched": False, "reason": f"候选：{e['name']}"}
    return {"ok": True, "unmatched": True, "reason": "没有员工的工作记录与任务匹配"}


def get_unmatched_tasks():
    """经理端：无人接手的任务列表。"""
    conn = get_conn()
    rows = conn.execute("SELECT * FROM agent_tasks WHERE status='unmatched' ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def publish_to_hall(task_id, candidate_ids):
    """经理选候选人后，把无人接手的任务发布到任务大厅。"""
    conn = get_conn()
    task = conn.execute("SELECT * FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
    if not task:
        conn.close()
        return {"ok": False, "msg": "任务不存在"}
    if task["status"] != "unmatched":
        conn.close()
        return {"ok": False, "msg": "任务不在「无人接手」状态"}
    conn.execute("UPDATE agent_tasks SET status='hall', candidates=? WHERE id=?",
                 (json.dumps(list(candidate_ids or [])), task_id))
    conn.commit()
    conn.close()
    return {"ok": True, "task_id": task_id, "status": "hall"}


def get_hall_tasks(user_id):
    """任务大厅：返回该用户作为候选人的待接取任务。"""
    conn = get_conn()
    rows = conn.execute("SELECT * FROM agent_tasks WHERE status='hall' ORDER BY id DESC").fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        try:
            cands = json.loads(d.get("candidates") or "[]")
        except Exception:  # noqa: BLE001
            cands = []
        if user_id in cands:
            d["candidates"] = cands
            out.append(d)
    return out


def claim_task(task_id, user_id):
    """候选人接取大厅任务 → 分发给自己 agent，进入报价流程。"""
    conn = get_conn()
    task = conn.execute("SELECT * FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
    if not task or task["status"] != "hall":
        conn.close()
        return {"ok": False, "msg": "任务不在大厅待接取状态"}
    task = dict(task)
    try:
        cands = json.loads(task.get("candidates") or "[]")
    except Exception:  # noqa: BLE001
        cands = []
    if user_id not in cands:
        conn.close()
        return {"ok": False, "msg": "你不是该任务的候选人"}
    agent = get_agent_by_user(user_id)
    if not agent:
        conn.close()
        return {"ok": False, "msg": "你没有专属 Agent"}
    conn.execute("UPDATE agent_tasks SET status='distributed', assignee_agent=?, candidates='[]' WHERE id=?",
                 (agent["id"], task_id))
    conn.commit()
    conn.close()
    return {"ok": True, "task_id": task_id, "agent_id": agent["id"], "status": "distributed"}


# ---------------------------------------------------------------------------
# 外包大厅（跨公司接单）
# ---------------------------------------------------------------------------
def get_outsource_tasks():
    """外包大厅：所有待接取的外包任务（附原公司名与负责人名）。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT t.*, c.name AS company_name, u.name AS manager_name, "
        "       u.company_id AS task_company_id "
        "FROM agent_tasks t "
        "LEFT JOIN agents a ON a.id = t.manager_agent "
        "LEFT JOIN users u ON u.id = a.user_id "
        "LEFT JOIN companies c ON c.id = u.company_id "
        "WHERE t.status='outsource' ORDER BY t.id DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def accept_outsource(task_id, user_id):
    """其他公司的人接取外包任务 → 分发给自己 agent，进入报价流程。"""
    conn = get_conn()
    task = conn.execute("SELECT * FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
    if not task or task["status"] != "outsource":
        conn.close()
        return {"ok": False, "msg": "任务不在外包大厅待接取状态"}
    task = dict(task)

    user = conn.execute("SELECT company_id FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        conn.close()
        return {"ok": False, "msg": "用户不存在"}
    user_company = user["company_id"]

    # 任务原公司（通过 manager_agent 找到）
    mgr = conn.execute(
        "SELECT u.company_id FROM agents a JOIN users u ON u.id=a.user_id WHERE a.id=?",
        (task.get("manager_agent"),)).fetchone()
    task_company = mgr["company_id"] if mgr else None

    if task_company is not None and user_company == task_company:
        conn.close()
        return {"ok": False, "msg": "不能接自己公司的外包任务"}

    agent = conn.execute("SELECT * FROM agents WHERE user_id=?", (user_id,)).fetchone()
    if not agent:
        conn.close()
        return {"ok": False, "msg": "你没有专属 Agent，无法接取"}

    conn.execute(
        "UPDATE agent_tasks SET status='distributed', assignee_agent=?, "
        "outsource_accepter=?, outsource_accepter_company=? WHERE id=?",
        (agent["id"], user_id, user_company, task_id))
    conn.commit()
    conn.close()
    return {"ok": True, "task_id": task_id, "agent_id": agent["id"], "status": "distributed"}


def add_task(title, detail="", difficulty=0.5, manager_agent_id=None):
    """新建一个任务（可直接入库），返回任务 dict"""
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO agent_tasks (title, detail, difficulty, status, manager_agent) "
        "VALUES (?,?,?,?,?)",
        (title, detail, difficulty, "pending", manager_agent_id),
    )
    conn.commit()
    tid = cur.lastrowid
    conn.close()
    return {"id": tid, "title": title, "detail": detail, "difficulty": difficulty,
            "status": "pending", "manager_agent": manager_agent_id}


def list_agents():
    """所有 Agent（附用户名/岗位/公司），经理分发任务时选择。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT a.*, u.name AS user_name, u.position, u.company_id "
        "FROM agents a LEFT JOIN users u ON u.id = a.user_id ORDER BY a.id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_internal_tasks():
    """待经理分发的内部任务（status=internal）。"""
    conn = get_conn()
    rows = conn.execute("SELECT * FROM agent_tasks WHERE status='internal' ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_estimated_tasks():
    """待经理审核报价的任务（status=estimated）。"""
    conn = get_conn()
    rows = conn.execute("SELECT * FROM agent_tasks WHERE status='estimated' ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def distribute_task(agent_id, task_id):
    """经理 agent 把任务分发（distributed）给某个员工 agent。

    这一步只是「分发」，任务真正落到员工头上要等员工 agent 报价、经理审核通过后。
    """
    conn = get_conn()
    task = conn.execute("SELECT * FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
    if not task:
        conn.close()
        return {"ok": False, "msg": "任务不存在"}
    if task["status"] == "done":
        conn.close()
        return {"ok": False, "msg": "任务已完成，不能重复分发"}
    conn.execute("UPDATE agent_tasks SET assignee_agent=?, status='distributed' WHERE id=?",
                 (agent_id, task_id))
    conn.commit()
    conn.close()
    return {"ok": True, "task_id": task_id, "assignee_agent": agent_id,
            "status": "distributed"}


# ---------------------------------------------------------------------------
# 本地记录（员工个人档案 / 技能 / 历史绩效，agent 报价依据）
# ---------------------------------------------------------------------------
def get_user_records(user_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM user_records WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else {"user_id": user_id, "content": ""}


def save_user_records(user_id, content):
    conn = get_conn()
    conn.execute(
        "INSERT INTO user_records (user_id, content, updated_at) VALUES (?,?,datetime('now','localtime')) "
        "ON CONFLICT(user_id) DO UPDATE SET content=excluded.content, "
        "updated_at=excluded.updated_at",
        (user_id, content or ""),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "user_id": user_id}


# ---------------------------------------------------------------------------
# 知识库①：工作记录（员工导入，供 Agent 分析任务适配度）
# ---------------------------------------------------------------------------
def add_work_record(user_id, content):
    content = (content or "").strip()
    if not content:
        return {"ok": False, "msg": "工作记录内容为空"}
    conn = get_conn()
    cur = conn.execute("INSERT INTO work_records (user_id, content) VALUES (?,?)", (user_id, content))
    conn.commit()
    conn.close()
    return {"ok": True, "id": cur.lastrowid}


def get_work_records(user_id):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM work_records WHERE user_id=? ORDER BY id DESC", (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_work_record(record_id):
    conn = get_conn()
    conn.execute("DELETE FROM work_records WHERE id=?", (record_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


# ---------------------------------------------------------------------------
# 知识库②：任务条件（公司级，经理维护；员工 Agent 查询，缺失则通知经理）
# ---------------------------------------------------------------------------
def add_task_condition(company_id, keywords, conditions):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO task_conditions (company_id, keywords, conditions) VALUES (?,?,?)",
        (company_id, (keywords or "").strip(), (conditions or "").strip()),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "id": cur.lastrowid}


def get_task_conditions(company_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM task_conditions WHERE company_id=? OR company_id IS NULL ORDER BY id DESC",
        (company_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_task_condition(cond_id):
    conn = get_conn()
    conn.execute("DELETE FROM task_conditions WHERE id=?", (cond_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


def query_task_conditions(task_title, task_detail, company_id):
    """员工 Agent 向总 Agent 查询任务条件：关键词匹配任务条件库，返回匹配的条件文本列表。"""
    conds = get_task_conditions(company_id)
    text = (task_title or "") + " " + (task_detail or "")
    matched = []
    for c in conds:
        kws = [k.strip() for k in (c.get("keywords") or "").replace("，", ",").split(",") if k.strip()]
        if kws and any(k in text for k in kws):
            matched.append(c.get("conditions") or "")
    return matched


# ---------------------------------------------------------------------------
# 通知（总 Agent 向经理发信息）
# ---------------------------------------------------------------------------
def create_notification(user_id, content, task_id=None):
    conn = get_conn()
    cur = conn.execute("INSERT INTO notifications (user_id, content, task_id) VALUES (?,?,?)",
                       (user_id, content, task_id))
    conn.commit()
    conn.close()
    return {"ok": True, "id": cur.lastrowid}


def get_notifications(user_id, unread_only=False):
    conn = get_conn()
    sql = "SELECT * FROM notifications WHERE user_id=?"
    if unread_only:
        sql += " AND is_read=0"
    rows = conn.execute(sql + " ORDER BY id DESC", (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_notifications_read(user_id):
    conn = get_conn()
    conn.execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


# ---------------------------------------------------------------------------
# 员工 agent 报价 + 经理审核报价
# ---------------------------------------------------------------------------
def _estimate_with_llm(task, context, base_salary):
    """让 LLM 结合任务 + 员工记录，给出工时/报价/适配度。返回 dict。

    context = 员工本地记录 + 工作记录拼接。
    """
    try:
        from llm import chat as llm_chat
        system = (
            "你是员工专属 Agent 的报价助手。根据任务要求、员工的本地记录和工作记录，"
            "完成三件事：1) 判断这个任务适不适合该员工做（适合/勉强/不适合）；"
            "2) 估算完成该任务所需工时（小时，数字）；3) 估算合理报价工资（元，数字）。"
            "只返回 JSON：{\"hours\":数字, \"wage\":数字, \"reason\":\"报价理由\", "
            "\"suitability\":\"适合/勉强/不适合\", \"suitability_reason\":\"适配判断理由\"}，不要输出多余文字。"
        )
        user = (
            f"任务标题：{task['title']}\n任务要求：{task.get('detail') or ''}\n"
            f"员工记录：{context or '（暂无）'}"
        )
        resp = llm_chat([{"role": "system", "content": system}, {"role": "user", "content": user}])
        data = _extract_json(getattr(resp, "content", None))
        if isinstance(data, dict):
            hours = float(data.get("hours", 0) or 0)
            wage = float(data.get("wage", 0) or 0)
            if hours > 0 and wage > 0:
                return {
                    "hours": hours, "wage": wage,
                    "reason": str(data.get("reason", "")),
                    "suitability": str(data.get("suitability", "适合") or "适合"),
                    "suitability_reason": str(data.get("suitability_reason", "")),
                }
    except Exception as e:  # noqa: BLE001
        print(f"[estimate] LLM 报价失败，走兜底公式：{e}")
    difficulty = float(task.get("difficulty") or 0.5)
    hours = round(2 + difficulty * 16, 1)
    wage = price_task(base_salary, difficulty)
    return {"hours": hours, "wage": wage, "reason": "按基础工资与难度系数估算",
            "suitability": "适合", "suitability_reason": "按难度系数估算"}


def estimate_task(agent_id, task_id):
    """员工 agent 审核任务并报价：结合本地记录+工作记录给出适配度、工时、工资，
    并向总 Agent 查询任务条件（缺失则通知经理）。状态 -> estimated。"""
    conn = get_conn()
    task = conn.execute("SELECT * FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
    agent = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
    conn.close()
    if not task or not agent:
        return {"ok": False, "msg": "任务或 Agent 不存在"}
    task = dict(task)
    agent = dict(agent)

    # 知识库①：本地记录 + 工作记录 + 能力知识库(RAG) → 适配度 & 报价
    profile = get_user_records(agent["user_id"])["content"]
    works = "；".join(r["content"] for r in get_work_records(agent["user_id"]))
    kb_text = "无"
    try:
        import ability_kb
        kb_hits = ability_kb.search(agent["user_id"], f"{task['title']} {task.get('detail') or ''}", top_k=3)
        if kb_hits:
            kb_text = "\n".join(f"- {t}" for t, _ in kb_hits)
    except Exception as e:  # noqa: BLE001
        print(f"[estimate] 能力知识库检索失败：{e}")
    context = f"本地记录：{profile or '无'}\n工作记录：{works or '无'}\n能力知识库：{kb_text}"
    salary = get_salary(agent["user_id"])
    base = float(salary["base_salary"] or 6000)
    est = _estimate_with_llm(task, context, base)

    # 知识库②：向总 Agent 查询任务条件
    conn = get_conn()
    urow = conn.execute("SELECT company_id FROM users WHERE id=?", (agent["user_id"],)).fetchone()
    company_id = dict(urow)["company_id"] if urow else None
    matched = query_task_conditions(task["title"], task.get("detail") or "", company_id)
    conditions_text = "\n".join(matched) if matched else ""
    needs = 1 if not matched else 0

    conn.execute(
        "UPDATE agent_tasks SET estimated_hours=?, estimated_wage=?, estimate_reason=?, "
        "suitability=?, suitability_reason=?, conditions=?, needs_conditions=?, status='estimated' WHERE id=?",
        (est["hours"], est["wage"], est["reason"], est["suitability"], est["suitability_reason"],
         conditions_text, needs, task_id),
    )
    # 缺失条件 → 通知经理补充
    if needs:
        mgr = conn.execute("SELECT manager_id FROM companies WHERE id=?", (company_id,)).fetchone()
        if mgr and mgr["manager_id"]:
            create_notification(mgr["manager_id"],
                                f"员工 Agent 请求任务「{task['title']}」的完成条件，条件库暂无记录，请补充。",
                                task_id)
    conn.commit()
    conn.close()

    return {"ok": True, "task_id": task_id, "hours": est["hours"], "wage": est["wage"],
            "reason": est["reason"], "suitability": est["suitability"],
            "suitability_reason": est["suitability_reason"],
            "conditions": conditions_text, "needs_conditions": needs}


def review_estimate(task_id, approve):
    """经理 agent 审核报价：通过 → assigned 并锁定 agreed_wage；打回 → distributed 重新报价。"""
    conn = get_conn()
    task = conn.execute("SELECT * FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
    if not task:
        conn.close()
        return {"ok": False, "msg": "任务不存在"}
    task = dict(task)
    if task["status"] != "estimated":
        conn.close()
        return {"ok": False, "msg": "任务当前不在待审核报价状态"}
    if approve:
        conn.execute("UPDATE agent_tasks SET status='assigned', agreed_wage=estimated_wage WHERE id=?",
                     (task_id,))
        msg = f"报价已通过，任务正式派发，工资 {task['estimated_wage']}"
    else:
        conn.execute("UPDATE agent_tasks SET status='distributed' WHERE id=?", (task_id,))
        msg = "报价已打回，可重新报价"
    conn.commit()
    conn.close()
    return {"ok": True, "task_id": task_id, "msg": msg}


def get_task(agent_id):
    """返回派给该 agent 且尚未完成的任务列表"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM agent_tasks WHERE assignee_agent=? AND status!='done' ORDER BY id DESC",
        (agent_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def submit_work(task_id, agent_id, content, images=None):
    """员工提交成果：写入 submissions（可附照片凭证），任务状态 -> submitted。"""
    conn = get_conn()
    task = conn.execute("SELECT * FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
    if not task:
        conn.close()
        return {"ok": False, "msg": "任务不存在"}
    imgs = json.dumps(list(images or []), ensure_ascii=False)
    cur = conn.execute(
        "INSERT INTO submissions (task_id, agent_id, content, status, images) VALUES (?,?,?,?,?)",
        (task_id, agent_id, content, "pending", imgs),
    )
    conn.execute("UPDATE agent_tasks SET status='submitted' WHERE id=?", (task_id,))
    conn.commit()
    sid = cur.lastrowid
    conn.close()
    return {"ok": True, "id": sid, "task_id": task_id, "agent_id": agent_id,
            "content": content, "status": "pending", "images": list(images or [])}


# ---------------------------------------------------------------------------
# 定价与工资
# ---------------------------------------------------------------------------
def price_task(base_salary, difficulty):
    """绩效标价 = base_salary × 难度系数。
    难度系数 = 0.5 + difficulty * 2.5（difficulty 取值范围 0~1，自动截断）。
    """
    difficulty = max(0.0, min(1.0, float(difficulty)))
    factor = 0.5 + difficulty * 2.5
    return round(float(base_salary) * factor, 2)


def update_salary(user_id, base_salary, exempt=0):
    """更新（或写入）员工工资：base_salary 与 exempt（是否豁免绩效）。"""
    conn = get_conn()
    try:
        conn.execute("INSERT INTO salaries (user_id, base_salary, exempt) VALUES (?,?,?)",
                     (user_id, base_salary, int(exempt)))
    except sqlite3.IntegrityError:
        conn.execute(
            "UPDATE salaries SET base_salary=?, exempt=?, updated_at=datetime('now','localtime') "
            "WHERE user_id=?",
            (base_salary, int(exempt), user_id),
        )
    conn.commit()
    conn.close()
    return {"user_id": user_id, "base_salary": base_salary, "exempt": int(exempt)}


def review_submission(submission_id, approve, exempt=0):
    """审核提交。

    approve=True：通过，任务 -> done，按（豁免 ? 基础工资 : 绩效标价）定价；
    approve=False：打回，任务 -> pending。
    exempt=1 时价格 = 基础工资（经理豁免白名单）。
    """
    conn = get_conn()
    sub = conn.execute("SELECT * FROM submissions WHERE id=?", (submission_id,)).fetchone()
    if not sub:
        conn.close()
        return {"ok": False, "msg": "提交不存在"}
    sub = dict(sub)

    task = conn.execute("SELECT * FROM agent_tasks WHERE id=?", (sub["task_id"],)).fetchone()
    if not task:
        conn.close()
        return {"ok": False, "msg": "任务不存在"}
    task = dict(task)

    agent = conn.execute("SELECT * FROM agents WHERE id=?", (sub["agent_id"],)).fetchone()
    agent = dict(agent) if agent else None
    base = 0
    if agent:
        salary = conn.execute("SELECT * FROM salaries WHERE user_id=?",
                              (agent["user_id"],)).fetchone()
        base = dict(salary)["base_salary"] if salary else 0

    if approve:
        # 优先用「报价审核通过后锁定的 agreed_wage」，其次按豁免/难度公式
        agreed = task.get("agreed_wage")
        if agreed is not None and float(agreed) > 0:
            price = round(float(agreed), 2)
        elif exempt:
            price = round(float(base), 2)
        else:
            difficulty = task.get("difficulty") or 0.5
            price = price_task(base, difficulty)
        conn.execute("UPDATE submissions SET status='approved', price=? WHERE id=?",
                     (price, submission_id))
        conn.execute("UPDATE agent_tasks SET status='done' WHERE id=?", (task["id"],))
        # 审核通过 → 生成一条待打款的结算记录
        if agent:
            conn.execute(
                "INSERT INTO payouts (submission_id, user_id, agent_id, amount, status) "
                "VALUES (?,?,?,?, 'pending') "
                "ON CONFLICT(submission_id) DO UPDATE SET amount=excluded.amount, status='pending'",
                (submission_id, agent["user_id"], agent["id"], price),
            )
        msg = f"✅ 已通过，绩效标价 {price}"
    else:
        price = 0
        conn.execute("UPDATE submissions SET status='rejected' WHERE id=?", (submission_id,))
        conn.execute("UPDATE agent_tasks SET status='pending' WHERE id=?", (task["id"],))
        msg = "⏪ 已打回，任务回到 pending 重新处理"

    conn.commit()
    conn.close()
    return {"ok": True, "msg": msg, "approve": bool(approve), "exempt": bool(exempt),
            "price": price, "task_id": task["id"]}


# ---------------------------------------------------------------------------
# 查询接口（供员工端「我的任务/我的工资」与经理端「工作台/审核」使用）
# ---------------------------------------------------------------------------
def get_salary(user_id):
    """查询员工工资。无记录返回默认 0，避免前端空指针。"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM salaries WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else {"user_id": user_id, "base_salary": 0, "exempt": 0}


def get_agent_tasks(agent_id):
    """返回派给该 agent 的任务，并附上最近一次提交的状态与标价。

    这是员工「我的任务」的数据源：任务列表 + 提交反馈（状态 / 绩效价）。
    """
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM agent_tasks WHERE assignee_agent=? ORDER BY id DESC",
        (agent_id,),
    ).fetchall()
    out = []
    for t in rows:
        t = dict(t)
        sub = conn.execute(
            "SELECT status, price, images FROM submissions WHERE task_id=? AND agent_id=? "
            "ORDER BY id DESC LIMIT 1",
            (t["id"], agent_id),
        ).fetchone()
        t["submission_status"] = dict(sub)["status"] if sub else None
        t["submission_price"] = dict(sub)["price"] if sub else None
        if sub:
            try:
                t["submission_images"] = json.loads(dict(sub).get("images") or "[]")
            except Exception:  # noqa: BLE001
                t["submission_images"] = []
        else:
            t["submission_images"] = []
        out.append(t)
    conn.close()
    return out


def get_pending_submissions():
    """经理审核：所有待审核的提交，附任务标题与提交员工。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT s.id AS sid, s.content, s.status, s.price, s.images, "
        "       t.title AS task_title, t.difficulty, "
        "       a.name AS agent_name, a.user_id AS submitter_user_id, "
        "       u.name AS submitter_name, u.position AS submitter_position "
        "FROM submissions s "
        "JOIN agent_tasks t ON t.id = s.task_id "
        "JOIN agents a ON a.id = s.agent_id "
        "LEFT JOIN users u ON u.id = a.user_id "
        "WHERE s.status='pending' ORDER BY s.id DESC"
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["images"] = json.loads(d.get("images") or "[]")
        except Exception:  # noqa: BLE001
            d["images"] = []
        out.append(d)
    return out


def count_agents():
    """团队 Agent 总数（经理工作台用）。"""
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) AS c FROM agents").fetchone()["c"]
    conn.close()
    return n


# ---------------------------------------------------------------------------
# 工资结算 / 打款
# ---------------------------------------------------------------------------
def get_payouts(status=None):
    """结算记录列表。可选 status 过滤（pending / paid）。附员工姓名。"""
    conn = get_conn()
    sql = (
        "SELECT p.*, u.name AS user_name, t.title AS task_title "
        "FROM payouts p "
        "LEFT JOIN users u ON u.id = p.user_id "
        "LEFT JOIN agent_tasks t ON t.id = (SELECT task_id FROM submissions WHERE id=p.submission_id) "
    )
    if status:
        sql += " WHERE p.status=?"
        rows = conn.execute(sql + " ORDER BY p.id DESC", (status,)).fetchall()
    else:
        rows = conn.execute(sql + " ORDER BY p.id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_user_payouts(user_id):
    """某员工的到账记录（含打款状态与金额）。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT p.*, t.title AS task_title FROM payouts p "
        "LEFT JOIN submissions s ON s.id = p.submission_id "
        "LEFT JOIN agent_tasks t ON t.id = s.task_id "
        "WHERE p.user_id=? ORDER BY p.id DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def pay_payout(payout_id):
    """经理打款：pending → paid，记录打款时间。"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM payouts WHERE id=?", (payout_id,)).fetchone()
    if not row:
        conn.close()
        return {"ok": False, "msg": "结算记录不存在"}
    if dict(row)["status"] == "paid":
        conn.close()
        return {"ok": False, "msg": "该笔已打款，无需重复操作"}
    conn.execute(
        "UPDATE payouts SET status='paid', paid_at=datetime('now','localtime') WHERE id=?",
        (payout_id,),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "msg": "已打款"}


def get_payout_stats():
    """结算概览：待打款金额与已打款总额。"""
    conn = get_conn()
    pending = conn.execute(
        "SELECT COALESCE(SUM(amount),0) AS s FROM payouts WHERE status='pending'"
    ).fetchone()["s"]
    paid = conn.execute(
        "SELECT COALESCE(SUM(amount),0) AS s FROM payouts WHERE status='paid'"
    ).fetchone()["s"]
    conn.close()
    return {"pending_amount": round(float(pending), 2), "paid_amount": round(float(paid), 2)}


# ---------------------------------------------------------------------------
# Agent 消息
# ---------------------------------------------------------------------------
def message_between(from_agent, to_agent, content, priority=0):
    """agent 之间发消息（priority 越大越优先，经理指令优先）。"""
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO agent_messages (from_agent, to_agent, content, priority) VALUES (?,?,?,?)",
        (from_agent, to_agent, content, priority),
    )
    conn.commit()
    mid = cur.lastrowid
    conn.close()
    return {"id": mid, "from_agent": from_agent, "to_agent": to_agent,
            "content": content, "priority": priority}


# ---------------------------------------------------------------------------
# 查询工具（供 agent 使用）
# ---------------------------------------------------------------------------
def query_db(agent_id, sql):
    """只读查询数据库（仅允许 SELECT），供 query_db 工具使用。"""
    sql = (sql or "").strip()
    if not sql.upper().startswith("SELECT"):
        return {"error": "只允许 SELECT 查询"}
    conn = get_conn()
    try:
        cur = conn.execute(sql)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description] if cur.description else []
        data = [dict(zip(cols, r)) for r in rows]
        return {"columns": cols, "rows": data, "count": len(data)}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# ReAct 循环（基础版）
# ---------------------------------------------------------------------------
def _build_tool_schemas(tools):
    schemas = {
        "query_db": {
            "name": "query_db",
            "description": "查询数据库/知识库，输入只读的 SELECT 语句",
            "parameters": {"type": "object", "properties": {
                "sql": {"type": "string", "description": "只读 SELECT 查询语句"}},
                "required": ["sql"]},
        },
        "message_agent": {
            "name": "message_agent",
            "description": "给其他 agent 发消息",
            "parameters": {"type": "object", "properties": {
                "to_agent": {"type": "integer", "description": "收件 agent id"},
                "content": {"type": "string", "description": "消息内容"},
                "priority": {"type": "integer", "description": "优先级，越大越优先"}},
                "required": ["to_agent", "content"]},
        },
        "get_task": {
            "name": "get_task",
            "description": "领取/查看分配给自己的任务",
            "parameters": {"type": "object", "properties": {}},
        },
        "submit_work": {
            "name": "submit_work",
            "description": "提交工作成果",
            "parameters": {"type": "object", "properties": {
                "task_id": {"type": "integer", "description": "任务 id"},
                "content": {"type": "string", "description": "成果内容"}},
                "required": ["task_id", "content"]},
        },
        "review": {
            "name": "review",
            "description": "审核提交（仅经理可用）",
            "parameters": {"type": "object", "properties": {
                "submission_id": {"type": "integer", "description": "提交 id"},
                "approve": {"type": "boolean", "description": "true=通过, false=打回"},
                "exempt": {"type": "integer", "description": "1=豁免绩效(按基础工资)"}},
                "required": ["submission_id", "approve"]},
        },
    }
    return [{"type": "function", "function": schemas[t]} for t in tools if t in schemas]


def _parse_tool_call(tc):
    name = tc.function.name
    raw = tc.function.arguments
    if isinstance(raw, str):
        args = _extract_json(raw)
        args = args if isinstance(args, dict) else {}
    elif isinstance(raw, dict):
        args = raw
    else:
        args = {}
    return name, args


def _execute_tool(name, args, agent, tools):
    if name not in tools:
        return {"error": f"未授权工具 {name}"}
    aid = agent["id"]
    if name == "query_db":
        return query_db(aid, args.get("sql", ""))
    if name == "message_agent":
        return message_between(aid, args.get("to_agent"), args.get("content", ""),
                               args.get("priority", 0))
    if name == "get_task":
        return get_task(aid)
    if name == "submit_work":
        return submit_work(args.get("task_id"), aid, args.get("content", ""))
    if name == "review":
        return review_submission(args.get("submission_id"),
                                 bool(args.get("approve", True)),
                                 int(args.get("exempt", 0) or 0))
    return {"error": "未知工具"}


def run_agent_loop(agent_id, task_text=None, max_steps=5):
    """基础 ReAct 循环：让 agent 循环调用工具直到给出最终回答。

    max_steps 控制最大轮数。
    """
    import llm as llm_mod

    agent = get_agent(agent_id)
    if not agent:
        raise ValueError("agent 不存在")
    tools = agent_tools(agent_id)
    role = agent["role_type"]
    name = agent["name"]

    system = (
        f"你是 {name}（角色：{role}）。你可以调用工具完成任务。"
        "注意：经理指令优先于平级请求。完成任务后调用 submit_work 提交成果。"
    )
    messages = [{"role": "system", "content": system}]
    if task_text:
        messages.append({"role": "user", "content": task_text})

    tool_defs = _build_tool_schemas(tools)
    is_cloud = llm_mod.is_cloud()

    for _ in range(max_steps):
        resp = llm_mod.chat(messages, tools=tool_defs or None)
        content = getattr(resp, "content", None) or ""
        tool_calls = getattr(resp, "tool_calls", None)

        if not tool_calls:
            messages.append({"role": "assistant", "content": content})
            break

        if is_cloud:
            messages.append({
                "role": "assistant",
                "content": content,
                "tool_calls": [
                    {"id": getattr(tc, "id", None), "type": "function",
                     "function": {"name": tc.function.name,
                                  "arguments": tc.function.arguments}}
                    for tc in tool_calls
                ],
            })
        else:
            messages.append({
                "role": "assistant",
                "content": content,
                "tool_calls": [
                    {"function": {"name": tc.function.name,
                                  "arguments": tc.function.arguments}}
                    for tc in tool_calls
                ],
            })

        for tc in tool_calls:
            name2, args = _parse_tool_call(tc)
            result = _execute_tool(name2, args, agent, tools)
            tcid = getattr(tc, "id", None) or f"tool_{id(tc)}"
            messages.append({"role": "tool", "tool_call_id": tcid,
                             "content": json.dumps(result, ensure_ascii=False)})

    return messages


if __name__ == "__main__":
    from db import init_db

    init_agent_db()
    init_db()
    print("已建表：agents / agent_tasks / submissions / agent_messages / salaries")
