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
import os
import re
import time

from dbcore import get_conn, insert_id, ensure_column, IntegrityErrors

ROLE_TYPES = ("employee", "functional", "manager")

# Agent 可用工具（manager 额外多 review 与 query_secret_kb）
BASE_TOOLS = ["query_db", "message_agent", "get_task", "submit_work"]
MANAGER_TOOLS = ["review", "query_secret_kb"]

# 外包任务押金（元）。缴纳后即可接取；任务通过审核后原路退回。
OUTSOURCE_DEPOSIT = float(os.environ.get("OUTSOURCE_DEPOSIT", "100") or "100")

# 机密库「限时自由访问」粒度的默认时长（秒）。
SECRET_KB_GRANT_SECONDS = int(os.environ.get("SECRET_KB_GRANT_SECONDS", "3600") or "3600")


def init_agent_db():
    """建 5 张表：agents / agent_tasks / submissions / agent_messages / salaries"""
    conn = get_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS agents (
        id __PK__,
        user_id INTEGER NOT NULL UNIQUE,
        role_type TEXT NOT NULL,
        name TEXT NOT NULL,
        config TEXT DEFAULT '{}',
        created_at TEXT DEFAULT (__NOW__)
    );

    CREATE TABLE IF NOT EXISTS agent_tasks (
        id __PK__,
        title TEXT NOT NULL,
        detail TEXT DEFAULT '',
        difficulty REAL DEFAULT 0.5,
        status TEXT DEFAULT 'pending',
        assignee_role TEXT DEFAULT '',
        assignee_agent INTEGER,
        manager_agent INTEGER,
        classification TEXT DEFAULT '一般',
        created_at TEXT DEFAULT (__NOW__)
    );

    CREATE TABLE IF NOT EXISTS submissions (
        id __PK__,
        task_id INTEGER NOT NULL,
        agent_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        price REAL DEFAULT 0,
        created_at TEXT DEFAULT (__NOW__),
        FOREIGN KEY (task_id) REFERENCES agent_tasks(id)
    );

    CREATE TABLE IF NOT EXISTS agent_messages (
        id __PK__,
        from_agent INTEGER NOT NULL,
        to_agent INTEGER NOT NULL,
        content TEXT NOT NULL,
        priority INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (__NOW__)
    );

    CREATE TABLE IF NOT EXISTS salaries (
        user_id INTEGER PRIMARY KEY,
        base_salary REAL DEFAULT 0,
        exempt INTEGER DEFAULT 0,
        updated_at TEXT DEFAULT (__NOW__)
    );

    CREATE TABLE IF NOT EXISTS payouts (
        id __PK__,
        submission_id INTEGER NOT NULL UNIQUE,
        user_id INTEGER NOT NULL,
        agent_id INTEGER,
        amount REAL DEFAULT 0,
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT (__NOW__),
        paid_at TEXT
    );

    CREATE TABLE IF NOT EXISTS user_records (
        user_id INTEGER PRIMARY KEY,
        content TEXT DEFAULT '',
        updated_at TEXT DEFAULT (__NOW__)
    );

    CREATE TABLE IF NOT EXISTS work_records (
        id __PK__,
        user_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT DEFAULT (__NOW__)
    );

    CREATE TABLE IF NOT EXISTS task_conditions (
        id __PK__,
        company_id INTEGER,
        keywords TEXT DEFAULT '',
        conditions TEXT DEFAULT '',
        created_at TEXT DEFAULT (__NOW__)
    );

    CREATE TABLE IF NOT EXISTS notifications (
        id __PK__,
        user_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        task_id INTEGER,
        is_read INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (__NOW__)
    );

    CREATE TABLE IF NOT EXISTS secret_kb (
        id __PK__,
        company_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT DEFAULT (__NOW__)
    );

    CREATE TABLE IF NOT EXISTS secret_kb_requests (
        id __PK__,
        company_id INTEGER NOT NULL,
        agent_id INTEGER NOT NULL,
        query TEXT NOT NULL,
        why TEXT DEFAULT '',
        usage TEXT DEFAULT '',
        danger TEXT DEFAULT '',
        status TEXT DEFAULT 'pending',
        grant_mode TEXT DEFAULT 'once',
        grant_expires_at INTEGER,
        created_at TEXT DEFAULT (__NOW__),
        reviewed_at TEXT
    );

    CREATE TABLE IF NOT EXISTS deposits (
        id __PK__,
        task_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        amount REAL DEFAULT 0,
        status TEXT DEFAULT 'paid',
        created_at TEXT DEFAULT (__NOW__),
        UNIQUE (task_id, user_id)
    );
    """)
    conn.commit()
    # 迁移：agent_tasks 增加报价相关列
    for col, typ in [("estimated_hours", "REAL"), ("estimated_wage", "REAL"),
                     ("estimate_reason", "TEXT"), ("agreed_wage", "REAL"),
                     ("suitability", "TEXT"), ("suitability_reason", "TEXT"),
                     ("conditions", "TEXT"), ("needs_conditions", "INTEGER"),
                     ("candidates", "TEXT"), ("outsource_accepter", "INTEGER"),
                     ("outsource_accepter_company", "INTEGER")]:
        ensure_column(conn, "agent_tasks", col, typ)
    # 迁移：submissions 增加 images / stage / tech_reviewer 列
    ensure_column(conn, "submissions", "images", "TEXT DEFAULT '[]'")
    ensure_column(conn, "submissions", "stage", "TEXT DEFAULT 'submitted'")
    ensure_column(conn, "submissions", "tech_reviewer", "INTEGER")
    ensure_column(conn, "agent_tasks", "deposit", f"REAL DEFAULT {OUTSOURCE_DEPOSIT}")
    # 迁移：secret_kb_requests 增加审批粒度（once=仅本次 / window=限时自由访问）
    ensure_column(conn, "secret_kb_requests", "grant_mode", "TEXT DEFAULT 'once'")
    ensure_column(conn, "secret_kb_requests", "grant_expires_at", "INTEGER")
    conn.commit()
    conn.close()
    # 迁移：旧表没有 classification 列的话，ALTER TABLE 补上
    _migrate_agent_tasks_classification()


def _migrate_agent_tasks_classification():
    """老数据库的 agent_tasks 表可能没有 classification 列，补上（TEXT 默认 '一般'）。"""
    conn = get_conn()
    try:
        ensure_column(conn, "agent_tasks", "classification", "TEXT DEFAULT '一般'")
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
        aid = insert_id(
            conn,
            "INSERT INTO agents (user_id, role_type, name, config) VALUES (?,?,?,?)",
            (user_id, role_type, name, json.dumps(cfg, ensure_ascii=False)),
        )
        conn.commit()
    except IntegrityErrors:
        conn.close()
        raise ValueError(f"用户 {user_id} 已有员工Agent")
    conn.close()
    return {"id": aid, "user_id": user_id, "role_type": role_type,
            "name": name, "config": cfg}


def agent_tools(agent_id):
    """返回该 agent 的工具列表。

    所有 agent 都有：query_db / message_agent / get_task / submit_work；
    只有 manager 多 review / query_secret_kb（机密知识库仅经理可访问）。
    """
    agent = get_agent(agent_id)
    if not agent:
        return []
    tools = list(BASE_TOOLS)
    if agent["role_type"] == "manager":
        tools.extend(MANAGER_TOOLS)
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
        "否则判定为「一般」)、difficulty(难度，0~1 的小数，简单任务接近 0，困难任务接近 1)。"
        "只返回 JSON 数组，不要输出多余文字。"
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
            try:
                difficulty = max(0.0, min(1.0, float(item.get("difficulty", 0.5))))
            except (TypeError, ValueError):
                difficulty = 0.5
            tid = insert_id(
                conn,
                "INSERT INTO agent_tasks (title, detail, difficulty, assignee_role, status, "
                "manager_agent, classification) VALUES (?,?,?,?,?,?,?)",
                (sub_title, sub_detail, difficulty, assignee_role, "pending_classify",
                 manager_agent_id, classification),
            )
            created.append({
                "id": tid,
                "title": sub_title,
                "detail": sub_detail,
                "assignee_role": assignee_role,
                "classification": classification,
                "difficulty": difficulty,
                "status": "pending_classify",
                "manager_agent": manager_agent_id,
            })
        conn.commit()
        return created
    finally:
        conn.close()


# 外包门槛：只有"极其简单"（难度低于该值）且"不涉密"的任务才允许外包。
OUTSOURCE_MAX_DIFFICULTY = 0.34


def _outsource_suggestion(classification, difficulty):
    """外包要求：不涉密 + 极简单。返回 (建议, 理由)。"""
    try:
        d = float(difficulty)
    except (TypeError, ValueError):
        d = 0.5
    if classification == "机密":
        return "内部", "涉及公司机密，建议内部处理"
    if d < OUTSOURCE_MAX_DIFFICULTY:
        return "外包", "不涉密且简单，可外包"
    return "内部", "不涉密但不算简单，建议内部处理"


def can_outsource(classification, difficulty):
    """外包资格校验：必须不涉密且极其简单。返回 (ok, msg)。"""
    if classification == "机密":
        return False, "机密任务不可外包，只能内部分配"
    try:
        d = float(difficulty)
    except (TypeError, ValueError):
        d = 0.5
    if d >= OUTSOURCE_MAX_DIFFICULTY:
        return False, "任务不够简单，不可外包"
    return True, ""


def get_pending_classification(company_id=None):
    """查待经理确认分级（status=pending_classify）的子任务，含分类与外包建议。

    company_id 提供时仅返回本公司任务。
    """
    conn = get_conn()
    sql = "SELECT * FROM agent_tasks WHERE status='pending_classify'"
    if company_id:
        sql += (" AND manager_agent IN (SELECT a.id FROM agents a "
                "JOIN users u ON u.id=a.user_id WHERE u.company_id=?)")
        rows = conn.execute(sql + " ORDER BY id DESC", (company_id,)).fetchall()
    else:
        rows = conn.execute(sql + " ORDER BY id DESC").fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["suggestion"], d["suggestion_reason"] = _outsource_suggestion(
            d.get("classification"), d.get("difficulty"))
        out.append(d)
    return out


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
    task = dict(task)
    # 外包硬约束：不涉密 + 极其简单，否则拒绝
    if choice == "outsource":
        ok_out, msg_out = can_outsource(task.get("classification"), task.get("difficulty"))
        if not ok_out:
            conn.close()
            return {"ok": False, "msg": msg_out}
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


def get_agent_task(task_id):
    """按 id 查 agent_tasks，返回 dict 或 None。"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_submission(submission_id):
    """按 id 查 submissions，返回 dict 或 None。"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM submissions WHERE id=?", (submission_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_payout(payout_id):
    """按 id 查 payouts，返回 dict 或 None。"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM payouts WHERE id=?", (payout_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


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


def _task_manager_user_id(task):
    """通过任务挂的经理 agent 找到经理用户 id。"""
    conn = get_conn()
    mid = task.get("manager_agent")
    row = None
    if mid:
        row = conn.execute("SELECT user_id FROM agents WHERE id=?", (mid,)).fetchone()
    conn.close()
    return dict(row)["user_id"] if row and row["user_id"] else None


def _agent_company_id(agent):
    """通过 agent 的 user_id 找到所属公司 id。"""
    conn = get_conn()
    row = conn.execute("SELECT company_id FROM users WHERE id=?", (agent["user_id"],)).fetchone()
    conn.close()
    return dict(row)["company_id"] if row and row["company_id"] else None


def record_pricing_decision(manager_user_id, task_title, difficulty, original, final):
    """把经理的定价决定写进经理 agent 的能力知识库（RAG），供后续定价参考。"""
    if not manager_user_id:
        return
    try:
        import ability_kb
        text = (f"定价决策：任务「{task_title}」难度 {difficulty}，"
                f"员工报价 {original}，经理定价 {final}。")
        ability_kb.add(manager_user_id, [text])
    except Exception as e:  # noqa: BLE001
        print(f"[pricing] 记录定价决策失败：{e}")


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


def get_unmatched_tasks(company_id=None):
    """经理端：无人接手的任务列表。company_id 提供时仅本公司。"""
    conn = get_conn()
    sql = "SELECT * FROM agent_tasks WHERE status='unmatched'"
    cond, params = _task_company_cond(company_id)
    if cond:
        sql += " AND " + cond
        rows = conn.execute(sql + " ORDER BY id DESC", tuple(params)).fetchall()
    else:
        rows = conn.execute(sql + " ORDER BY id DESC").fetchall()
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
def get_outsource_tasks(user_id=None):
    """外包大厅：所有待接取的外包任务（附原公司名、负责人名、押金与本人缴纳状态）。"""
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
    out = []
    for r in rows:
        d = dict(r)
        d["deposit"] = float(d.get("deposit") or OUTSOURCE_DEPOSIT)
        d["deposit_paid"] = False
        if user_id:
            dep = conn.execute(
                "SELECT id FROM deposits WHERE task_id=? AND user_id=? AND status='paid'",
                (d["id"], user_id)).fetchone()
            d["deposit_paid"] = dep is not None
        out.append(d)
    conn.close()
    return out


def pay_outsource_deposit(task_id, user_id):
    """缴纳外包任务押金（模拟支付）。返回 (ok, msg)。

    任何已登录用户都可缴纳押金；缴纳后才有资格接取该外包任务。
    """
    conn = get_conn()
    task = conn.execute("SELECT * FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
    if not task or task["status"] != "outsource":
        conn.close()
        return {"ok": False, "msg": "任务不在外包大厅待接取状态"}
    user = conn.execute("SELECT id FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        conn.close()
        return {"ok": False, "msg": "用户不存在"}
    amount = float(dict(task).get("deposit") or OUTSOURCE_DEPOSIT)
    conn.execute(
        "INSERT INTO deposits (task_id, user_id, amount, status) VALUES (?,?,?,'paid') "
        "ON CONFLICT(task_id, user_id) DO UPDATE SET amount=excluded.amount, status='paid'",
        (task_id, user_id, amount),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "msg": f"已缴纳押金 ¥{amount:.2f}，可接取该任务", "deposit": amount}


def get_outsource_deposit(task_id, user_id):
    """查询某用户对某外包任务是否已缴押金。返回 dict 或 None。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM deposits WHERE task_id=? AND user_id=? AND status='paid'",
        (task_id, user_id)).fetchone()
    conn.close()
    return dict(row) if row else None


def refund_outsource_deposit(task_id, user_id):
    """任务验收通过后原路退回押金。"""
    if not user_id:
        return
    conn = get_conn()
    conn.execute(
        "UPDATE deposits SET status='refunded' WHERE task_id=? AND user_id=? AND status='paid'",
        (task_id, user_id))
    conn.commit()
    conn.close()


def accept_outsource(task_id, user_id):
    """接取外包任务（所有人可接，但须先缴押金）→ 分发给自己 agent，进入报价流程。"""
    conn = get_conn()
    task = conn.execute("SELECT * FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
    if not task or task["status"] != "outsource":
        conn.close()
        return {"ok": False, "msg": "任务不在外包大厅待接取状态"}
    task = dict(task)

    user = conn.execute("SELECT company_id, role FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        conn.close()
        return {"ok": False, "msg": "用户不存在"}
    user_company = user["company_id"]

    # 不能接自己公司发布的外包任务（防止左手倒右手）
    pub_company = _task_company_id(task)
    if user_company is not None and pub_company is not None and pub_company == user_company:
        conn.close()
        return {"ok": False, "msg": "不能接取自己公司发布的任务"}

    agent = conn.execute("SELECT * FROM agents WHERE user_id=?", (user_id,)).fetchone()
    if not agent:
        conn.close()
        return {"ok": False, "msg": "你没有专属 Agent，无法接取"}

    # 押金门槛：必须先缴纳押金
    dep = conn.execute(
        "SELECT id FROM deposits WHERE task_id=? AND user_id=? AND status='paid'",
        (task_id, user_id)).fetchone()
    if not dep:
        conn.close()
        return {"ok": False, "msg": "请先缴纳押金再接取该任务"}

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
    tid = insert_id(
        conn,
        "INSERT INTO agent_tasks (title, detail, difficulty, status, manager_agent) "
        "VALUES (?,?,?,?,?)",
        (title, detail, difficulty, "pending", manager_agent_id),
    )
    conn.commit()
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


def _task_company_cond(company_id):
    """返回 (sql_where_fragment, params)：按公司过滤任务（任务挂的经理 agent 归属公司）。"""
    if not company_id:
        return "", []
    return ("manager_agent IN (SELECT a.id FROM agents a "
            "JOIN users u ON u.id=a.user_id WHERE u.company_id=?)", [company_id])


def get_internal_tasks(company_id=None):
    """待经理分发的内部任务（status=internal）。company_id 提供时仅本公司。"""
    conn = get_conn()
    sql = "SELECT * FROM agent_tasks WHERE status='internal'"
    cond, params = _task_company_cond(company_id)
    if cond:
        sql += " AND " + cond
        rows = conn.execute(sql + " ORDER BY id DESC", tuple(params)).fetchall()
    else:
        rows = conn.execute(sql + " ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_estimated_tasks(company_id=None):
    """待经理审核报价的任务（status=estimated）。company_id 提供时仅本公司。"""
    conn = get_conn()
    sql = "SELECT * FROM agent_tasks WHERE status='estimated'"
    cond, params = _task_company_cond(company_id)
    if cond:
        sql += " AND " + cond
        rows = conn.execute(sql + " ORDER BY id DESC", tuple(params)).fetchall()
    else:
        rows = conn.execute(sql + " ORDER BY id DESC").fetchall()
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
        "INSERT INTO user_records (user_id, content, updated_at) VALUES (?,?,__NOW__) "
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
    rid = insert_id(conn, "INSERT INTO work_records (user_id, content) VALUES (?,?)", (user_id, content))
    conn.commit()
    conn.close()
    return {"ok": True, "id": rid}


def get_work_records(user_id):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM work_records WHERE user_id=? ORDER BY id DESC", (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_work_record_owner(record_id):
    """返回工作记录归属用户的 company_id / id，供删除时校验。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT w.id, u.company_id FROM work_records w "
        "JOIN users u ON u.id = w.user_id WHERE w.id=?", (record_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_work_record(record_id, user_id=None):
    """删除工作记录；提供 user_id 时仅能删自己的（经理传 None 可删任意）。"""
    conn = get_conn()
    if user_id is not None:
        cur = conn.execute("DELETE FROM work_records WHERE id=? AND user_id=?", (record_id, user_id))
    else:
        cur = conn.execute("DELETE FROM work_records WHERE id=?", (record_id,))
    conn.commit()
    deleted = cur.rowcount
    conn.close()
    return {"ok": True, "deleted": deleted}


# ---------------------------------------------------------------------------
# 知识库②：任务条件（公司级，经理维护；员工 Agent 查询，缺失则通知经理）
# ---------------------------------------------------------------------------
def add_task_condition(company_id, keywords, conditions):
    conn = get_conn()
    cid = insert_id(
        conn,
        "INSERT INTO task_conditions (company_id, keywords, conditions) VALUES (?,?,?)",
        (company_id, (keywords or "").strip(), (conditions or "").strip()),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "id": cid}


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
# 知识库③：公司本地机密知识库（仅经理 Agent 可访问，且访问需经理逐次审批）
# ---------------------------------------------------------------------------
def add_secret_kb(company_id, content):
    """经理向本公司机密知识库写入一条。company_id 必须非空。"""
    content = (content or "").strip()
    if not content:
        return {"ok": False, "msg": "机密知识内容为空"}
    if not company_id:
        return {"ok": False, "msg": "缺少公司归属"}
    conn = get_conn()
    sid = insert_id(conn, "INSERT INTO secret_kb (company_id, content) VALUES (?,?)",
                    (company_id, content))
    conn.commit()
    conn.close()
    return {"ok": True, "id": sid}


def get_secret_kb(company_id):
    """列出本公司机密知识库全部条目。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, content, created_at FROM secret_kb WHERE company_id=? ORDER BY id DESC",
        (company_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_secret_kb(entry_id, company_id):
    """删除本公司机密知识库条目（仅本公司）。"""
    conn = get_conn()
    cur = conn.execute("DELETE FROM secret_kb WHERE id=? AND company_id=?",
                       (entry_id, company_id))
    conn.commit()
    deleted = cur.rowcount
    conn.close()
    return {"ok": True, "deleted": deleted}


def search_secret_kb(company_id, query, top_k=5):
    """经理 Agent 检索本公司机密知识库（关键词匹配，返回片段列表）。

    注意：业务上不应直接调用此函数，应走 access_secret_kb()，先经经理审批。
    """
    entries = get_secret_kb(company_id)
    if not query or not query.strip():
        return entries[:top_k]
    try:
        import jieba
        kws = [w for w in jieba.lcut(query) if len(w.strip()) >= 2]
    except Exception:  # noqa: BLE001
        kws = query.split()
    if not kws:
        return entries[:top_k]
    scored = []
    for e in entries:
        c = e["content"]
        score = sum(1 for k in kws if k in c)
        if score > 0:
            scored.append((score, e))
    scored.sort(key=lambda x: (-x[0], -x[1]["id"]))
    return [e for _, e in scored[:top_k]]


# ---- 机密库访问审批：agent 必须先发起申请，经理批准后才能读 ----
def request_secret_kb_access(agent_id, company_id, query, why, usage, danger):
    """经理 Agent 发起机密库访问申请。返回申请记录（status=pending）。"""
    query = (query or "").strip()
    if not query:
        return {"ok": False, "msg": "检索内容为空"}
    if not company_id:
        return {"ok": False, "msg": "缺少公司归属"}
    conn = get_conn()
    rid = insert_id(
        conn,
        "INSERT INTO secret_kb_requests (company_id, agent_id, query, why, usage, danger) "
        "VALUES (?,?,?,?,?,?)",
        (company_id, agent_id, query,
         (why or "").strip(), (usage or "").strip(), (danger or "").strip()),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "id": rid, "status": "pending",
            "msg": "已提交机密库访问申请，等待经理审批"}


def get_secret_kb_requests(company_id, status=None):
    """列出本公司机密库访问申请（经理审批用）。可按 status 过滤。"""
    conn = get_conn()
    sql = ("SELECT r.*, a.name AS agent_name FROM secret_kb_requests r "
           "LEFT JOIN agents a ON a.id = r.agent_id WHERE r.company_id=?")
    params = [company_id]
    if status:
        sql += " AND r.status=?"
        params.append(status)
    rows = conn.execute(sql + " ORDER BY r.id DESC", tuple(params)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def review_secret_kb_request(request_id, company_id, approve, grant_mode="once", grant_seconds=None):
    """经理审批机密库访问申请。

    approve=True 放行，False 拒绝。
    grant_mode（批准粒度，由经理自选）：
      - 'once'   ：仅放行本次 query（默认，最严格）
      - 'window' ：限时自由访问，grant_seconds 内该 agent 可任意检索（默认 SECRET_KB_GRANT_SECONDS）
    """
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM secret_kb_requests WHERE id=? AND company_id=?", (request_id, company_id)).fetchone()
    if not row:
        conn.close()
        return {"ok": False, "msg": "申请不存在"}
    if row["status"] != "pending":
        conn.close()
        return {"ok": False, "msg": "该申请已处理"}
    new_status = "approved" if approve else "rejected"
    if approve and grant_mode not in ("once", "window"):
        grant_mode = "once"
    expires = None
    if approve and grant_mode == "window":
        seconds = int(grant_seconds or SECRET_KB_GRANT_SECONDS)
        expires = int(time.time()) + seconds
    conn.execute(
        "UPDATE secret_kb_requests SET status=?, grant_mode=?, grant_expires_at=?, reviewed_at=__NOW__ WHERE id=?",
        (new_status, grant_mode if approve else row["grant_mode"], expires, request_id))
    conn.commit()
    conn.close()
    return {"ok": True, "status": new_status, "grant_mode": grant_mode if approve else None,
            "msg": f"已批准该访问（{'仅本次' if grant_mode == 'once' else '限时自由访问'}）" if approve else "已拒绝该访问"}


def access_secret_kb(agent_id, company_id, query, why, usage, danger):
    """经理 Agent 访问机密库的唯一入口。

    放行规则（任一命中即可）：
      1. 存在同 agent + 同 query 的 approved 申请（once 粒度）
      2. 存在同 agent 的 approved 申请且 grant_mode='window' 且未过期
    否则提交带「为什么需要 / 项目用途 / 潜在危险」的新申请，等待经理审批；
    未批准前不返回任何机密内容。
    """
    query = (query or "").strip()
    conn = get_conn()
    now = int(time.time())
    approved = conn.execute(
        "SELECT id, grant_mode, grant_expires_at FROM secret_kb_requests "
        "WHERE company_id=? AND agent_id=? AND status='approved' AND ("
        "  (query=? AND grant_mode='once') OR "
        "  (grant_mode='window' AND (grant_expires_at IS NULL OR grant_expires_at > ?))"
        ") ORDER BY id DESC LIMIT 1",
        (company_id, agent_id, query, now)).fetchone()
    conn.close()
    if approved:
        return {"ok": True, "status": "approved", "grant_mode": approved["grant_mode"],
                "hits": search_secret_kb(company_id, query)}
    # 无放行申请 → 提交新申请，等待经理审批
    return request_secret_kb_access(agent_id, company_id, query, why, usage, danger)


# ---------------------------------------------------------------------------
# 通知（总 Agent 向经理发信息）
# ---------------------------------------------------------------------------
def create_notification(user_id, content, task_id=None):
    conn = get_conn()
    nid = insert_id(conn, "INSERT INTO notifications (user_id, content, task_id) VALUES (?,?,?)",
                    (user_id, content, task_id))
    conn.commit()
    conn.close()
    return {"ok": True, "id": nid}


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

    报价护栏：LLM 报价若偏离算法区间（0.5~3 倍基础工资，或工时异常），
    视为"不好报价"，回退到难度系数公式，避免 LLM 拍出离谱价格。
    """
    difficulty = float(task.get("difficulty") or 0.5)
    formula_hours = round(2 + difficulty * 16, 1)
    formula_wage = price_task(base_salary, difficulty)
    wage_floor = round(float(base_salary) * 0.5, 2)
    wage_ceil = round(float(base_salary) * 3.0, 2)

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
            # 报价护栏：超出合理区间或工时异常 → 视为不好报价，回退公式
            if hours > 0 and wage > 0 and wage_floor <= wage <= wage_ceil and 0.5 <= hours <= 160:
                return {
                    "hours": hours, "wage": wage,
                    "reason": str(data.get("reason", "")),
                    "suitability": str(data.get("suitability", "适合") or "适合"),
                    "suitability_reason": str(data.get("suitability_reason", "")),
                }
            return {
                "hours": formula_hours, "wage": formula_wage,
                "reason": "LLM 报价超出合理区间，按算法公式估算",
                "suitability": str(data.get("suitability", "适合") or "适合"),
                "suitability_reason": str(data.get("suitability_reason", "")),
            }
    except Exception as e:  # noqa: BLE001
        print(f"[estimate] LLM 报价失败，走兜底公式：{e}")
    return {"hours": formula_hours, "wage": formula_wage,
            "reason": "按基础工资与难度系数估算",
            "suitability": "适合", "suitability_reason": "按难度系数估算"}


def estimate_task(agent_id, task_id):
    """员工 agent 审核任务并报价：结合本地记录+工作记录给出适配度、工时、工资，
    并向总 Agent 查询任务条件（缺失则通知经理）。状态 -> estimated。

    权责约束：只有被分派给该 agent 的任务、且处于待报价状态时才能报价。
    """
    conn = get_conn()
    task = conn.execute("SELECT * FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
    agent = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
    conn.close()
    if not task or not agent:
        return {"ok": False, "msg": "任务或 Agent 不存在"}
    task = dict(task)
    agent = dict(agent)
    # 权责：只能报价分派给自己的任务，且任务须处于待报价状态
    if task.get("assignee_agent") != agent_id:
        return {"ok": False, "msg": "任务未分派给你，无法报价"}
    if task["status"] != "distributed":
        return {"ok": False, "msg": "任务当前状态不允许报价"}

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


def review_estimate(task_id, approve, custom_wage=None):
    """经理 agent 审核报价：通过 → assigned 并锁定 agreed_wage（可手动改价）；打回 → 重新报价。

    custom_wage 提供且 >0 时，按经理改的价格锁定，并把决定记进经理 agent 的能力知识库。
    """
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
        wage = float(task.get("estimated_wage") or 0)
        changed = False
        if custom_wage is not None and float(custom_wage) > 0:
            wage = round(float(custom_wage), 2)
            changed = True
            record_pricing_decision(_task_manager_user_id(task), task["title"],
                                    task.get("difficulty") or 0.5,
                                    task.get("estimated_wage"), wage)
        if changed:
            # 经理改价 → 返还员工确认，协商一致才派发
            conn.execute("UPDATE agent_tasks SET agreed_wage=?, status='price_confirm' WHERE id=?",
                         (wage, task_id))
            msg = f"已按 {wage} 定价，等待员工确认"
        else:
            conn.execute("UPDATE agent_tasks SET status='assigned', agreed_wage=? WHERE id=?",
                         (wage, task_id))
            msg = f"报价已通过，任务正式派发，工资 {wage}"
    else:
        conn.execute("UPDATE agent_tasks SET status='distributed' WHERE id=?", (task_id,))
        msg = "报价已打回，可重新报价"
    conn.commit()
    conn.close()
    return {"ok": True, "task_id": task_id, "msg": msg}


def employee_confirm_price(task_id, user_id, agree):
    """员工确认经理改价：同意 → assigned；不同意 → estimated 返回经理重新定价。"""
    conn = get_conn()
    task = conn.execute("SELECT * FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
    if not task:
        conn.close()
        return {"ok": False, "msg": "任务不存在"}
    task = dict(task)
    if task["status"] != "price_confirm":
        conn.close()
        return {"ok": False, "msg": "任务不在待确认价格状态"}
    agent = get_agent_by_user(user_id)
    if not agent or agent["id"] != task.get("assignee_agent"):
        conn.close()
        return {"ok": False, "msg": "只有任务承接人才能确认价格"}
    if agree:
        conn.execute("UPDATE agent_tasks SET status='assigned' WHERE id=?", (task_id,))
        conn.commit()
        conn.close()
        return {"ok": True, "status": "assigned", "msg": "已同意，任务正式派发"}
    else:
        conn.execute("UPDATE agent_tasks SET status='estimated' WHERE id=?", (task_id,))
        conn.commit()
        conn.close()
        return {"ok": True, "status": "estimated", "msg": "已返回，等待经理重新定价"}


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
    """员工提交成果：写入 submissions（可附照片凭证），任务状态 -> submitted。

    权责约束：只有被分派给该 agent 的任务、且处于进行中/已打回状态时才能提交。
    """
    conn = get_conn()
    task = conn.execute("SELECT * FROM agent_tasks WHERE id=?", (task_id,)).fetchone()
    if not task:
        conn.close()
        return {"ok": False, "msg": "任务不存在"}
    task = dict(task)
    if task.get("assignee_agent") != agent_id:
        conn.close()
        return {"ok": False, "msg": "任务未分派给你，无法提交成果"}
    if task["status"] not in ("assigned", "rejected"):
        conn.close()
        return {"ok": False, "msg": "任务当前状态不允许提交成果"}
    imgs = json.dumps(list(images or []), ensure_ascii=False)
    sid = insert_id(
        conn,
        "INSERT INTO submissions (task_id, agent_id, content, status, images) VALUES (?,?,?,?,?)",
        (task_id, agent_id, content, "pending", imgs),
    )
    conn.execute("UPDATE agent_tasks SET status='submitted' WHERE id=?", (task_id,))
    conn.commit()
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
    conn.execute(
        "INSERT INTO salaries (user_id, base_salary, exempt) VALUES (?,?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET base_salary=excluded.base_salary, "
        "exempt=excluded.exempt, updated_at=__NOW__",
        (user_id, base_salary, int(exempt)),
    )
    conn.commit()
    conn.close()
    return {"user_id": user_id, "base_salary": base_salary, "exempt": int(exempt)}


def review_submission(submission_id, approve, exempt=0, custom_price=None):
    """审核提交。

    approve=True：通过，任务 -> done，按（豁免 ? 基础工资 : 绩效标价）定价；
    可传 custom_price 手动改价。approve=False：打回，任务 -> pending。
    exempt=1 时价格 = 基础工资（经理豁免白名单）。
    改价时会记进经理 agent 的能力知识库。
    """
    conn = get_conn()
    sub = conn.execute("SELECT * FROM submissions WHERE id=?", (submission_id,)).fetchone()
    if not sub:
        conn.close()
        return {"ok": False, "msg": "提交不存在"}
    sub = dict(sub)
    # 仅待审核的提交可被审核；已通过/已打回/已走四阶段流水线的提交不可重复审核
    if sub["status"] != "pending":
        conn.close()
        return {"ok": False, "msg": "该提交已处理，不能重复审核"}

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
        # 经理手动改价
        if custom_price is not None and float(custom_price) > 0:
            custom = round(float(custom_price), 2)
            if custom != price:
                record_pricing_decision(_task_manager_user_id(task), task["title"],
                                        task.get("difficulty") or 0.5, price, custom)
            price = custom
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
        # 外包任务验收通过 → 退回接单押金
        if task.get("outsource_accepter"):
            refund_outsource_deposit(task["id"], task["outsource_accepter"])
    else:
        price = 0
        conn.execute("UPDATE submissions SET status='rejected' WHERE id=?", (submission_id,))
        # 打回后回到 assigned，让员工可重新提交（与四阶段流水线保持一致，避免责任链断裂）
        conn.execute("UPDATE agent_tasks SET status='assigned' WHERE id=?", (task["id"],))
        msg = "⏪ 已打回，任务回到进行中，可重新提交"

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


def get_pending_submissions(company_id=None):
    """经理审核：待审核的提交，附任务标题、提交员工、当前阶段、指定技术员。

    company_id 提供时仅返回本公司提交，防止跨公司越权读取。
    """
    conn = get_conn()
    sql = (
        "SELECT s.id AS sid, s.content, s.status, s.price, s.images, s.stage, s.tech_reviewer, "
        "       t.title AS task_title, t.difficulty, "
        "       a.name AS agent_name, a.user_id AS submitter_user_id, "
        "       u.name AS submitter_name, u.position AS submitter_position, "
        "       tu.name AS tech_reviewer_name "
        "FROM submissions s "
        "JOIN agent_tasks t ON t.id = s.task_id "
        "JOIN agents a ON a.id = s.agent_id "
        "LEFT JOIN users u ON u.id = a.user_id "
        "LEFT JOIN users tu ON tu.id = s.tech_reviewer "
        "WHERE s.status='pending'"
    )
    if company_id:
        sql += " AND u.company_id=?"
        rows = conn.execute(sql + " ORDER BY s.id DESC", (company_id,)).fetchall()
    else:
        rows = conn.execute(sql + " ORDER BY s.id DESC").fetchall()
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


def count_agents(company_id=None):
    """团队 Agent 总数（经理工作台用）；company_id 提供时仅统计本公司。"""
    conn = get_conn()
    if company_id:
        n = conn.execute(
            "SELECT COUNT(*) AS c FROM agents a JOIN users u ON u.id=a.user_id "
            "WHERE u.company_id=?", (company_id,)).fetchone()["c"]
    else:
        n = conn.execute("SELECT COUNT(*) AS c FROM agents").fetchone()["c"]
    conn.close()
    return n


# ---------------------------------------------------------------------------
# 权责审核流水线（提交后四阶段）
# ① 员工 agent 自检 → ② 经理 agent 跑小项目测试 → ③ 经理核验 → ④ 技术员验证
# ---------------------------------------------------------------------------
def _llm_judge(submission, task, system_prompt):
    """用 LLM 判断成果是否合格/能否跑通，返回 (pass, reason)。"""
    try:
        from llm import chat as llm_chat
        user = (f"任务：{task['title']}\n任务要求：{task.get('detail') or ''}\n"
                f"员工提交内容：{submission['content']}")
        resp = llm_chat([{"role": "system", "content": system_prompt},
                         {"role": "user", "content": user}])
        data = _extract_json(getattr(resp, "content", None))
        if isinstance(data, dict) and "pass" in data:
            return bool(data["pass"]), str(data.get("reason", ""))
    except Exception as e:  # noqa: BLE001
        print(f"[judge] LLM 判断失败：{e}")
    return True, "LLM 判断失败，默认通过"


def _reject_submission(conn, submission_id, task_id):
    """打回：提交置 rejected，任务回到 assigned。"""
    conn.execute("UPDATE submissions SET status='rejected', stage='rejected' WHERE id=?", (submission_id,))
    conn.execute("UPDATE agent_tasks SET status='assigned' WHERE id=?", (task_id,))


def _get_sub_and_task(conn, submission_id):
    sub = conn.execute("SELECT * FROM submissions WHERE id=?", (submission_id,)).fetchone()
    if not sub:
        return None, None
    task = conn.execute("SELECT * FROM agent_tasks WHERE id=?", (sub["task_id"],)).fetchone()
    return dict(sub), dict(task) if task else None


def _reject_if_processed(sub):
    """四阶段流水线只允许处理 status=pending 的提交，避免与两阶段审核重复结算。"""
    if sub.get("status") != "pending":
        return {"ok": False, "msg": "该提交已处理，不能重复审核"}
    return None


def agent_check_submission(submission_id):
    """阶段①：员工 agent 自检，不合格直接打回。"""
    conn = get_conn()
    sub, task = _get_sub_and_task(conn, submission_id)
    if not sub or not task:
        conn.close()
        return {"ok": False, "msg": "提交或任务不存在"}
    processed = _reject_if_processed(sub)
    if processed:
        conn.close()
        return processed
    if sub["stage"] != "submitted":
        conn.close()
        return {"ok": False, "msg": "当前不是待员工 agent 检查阶段"}
    ok, reason = _llm_judge(sub, task,
        "你是员工 agent 自检助手。检查这份成果是否合格（完整、可执行、符合任务要求）。"
        "只返回 JSON：{\"pass\": true 或 false, \"reason\": \"一句话\"}")
    if ok:
        conn.execute("UPDATE submissions SET stage='agent_checked' WHERE id=?", (submission_id,))
        conn.commit()
        conn.close()
        return {"ok": True, "stage": "agent_checked", "pass": True, "reason": reason}
    _reject_submission(conn, submission_id, sub["task_id"])
    conn.commit()
    conn.close()
    return {"ok": True, "stage": "rejected", "pass": False, "reason": reason}


def manager_test_submission(submission_id):
    """阶段②：经理 agent 把成果带到小项目里跑一遍，跑通才确认。"""
    conn = get_conn()
    sub, task = _get_sub_and_task(conn, submission_id)
    if not sub or not task:
        conn.close()
        return {"ok": False, "msg": "提交或任务不存在"}
    processed = _reject_if_processed(sub)
    if processed:
        conn.close()
        return processed
    if sub["stage"] != "agent_checked":
        conn.close()
        return {"ok": False, "msg": "当前不是待经理 agent 跑测试阶段"}
    ok, reason = _llm_judge(sub, task,
        "你是经理 agent 测试助手。把这份成果放进一个小项目里实际跑一遍，判断能否跑通（能正常使用/运行）。"
        "只返回 JSON：{\"pass\": true 或 false, \"reason\": \"一句话\"}")
    if ok:
        conn.execute("UPDATE submissions SET stage='manager_tested' WHERE id=?", (submission_id,))
        conn.commit()
        conn.close()
        return {"ok": True, "stage": "manager_tested", "pass": True, "reason": reason}
    _reject_submission(conn, submission_id, sub["task_id"])
    conn.commit()
    conn.close()
    return {"ok": True, "stage": "rejected", "pass": False, "reason": reason}


def manager_verify_submission(submission_id, approve, custom_price=None):
    """阶段③：经理人工核验（可改价）。"""
    conn = get_conn()
    sub, task = _get_sub_and_task(conn, submission_id)
    if not sub or not task:
        conn.close()
        return {"ok": False, "msg": "提交或任务不存在"}
    processed = _reject_if_processed(sub)
    if processed:
        conn.close()
        return processed
    if sub["stage"] != "manager_tested":
        conn.close()
        return {"ok": False, "msg": "当前不是待经理核验阶段"}
    if not approve:
        _reject_submission(conn, submission_id, sub["task_id"])
        conn.commit()
        conn.close()
        return {"ok": True, "stage": "rejected", "msg": "已打回"}
    if custom_price is not None and float(custom_price) > 0:
        conn.execute("UPDATE submissions SET price=? WHERE id=?",
                     (round(float(custom_price), 2), submission_id))
    conn.execute("UPDATE submissions SET stage='manager_verified' WHERE id=?", (submission_id,))
    conn.commit()
    conn.close()
    return {"ok": True, "stage": "manager_verified", "msg": "经理已核验"}


def designate_tech_reviewer(submission_id, user_id):
    """经理指定技术人员来验证。"""
    conn = get_conn()
    sub = conn.execute("SELECT * FROM submissions WHERE id=?", (submission_id,)).fetchone()
    if not sub:
        conn.close()
        return {"ok": False, "msg": "提交不存在"}
    conn.execute("UPDATE submissions SET tech_reviewer=? WHERE id=?", (user_id, submission_id))
    conn.commit()
    conn.close()
    return {"ok": True, "submission_id": submission_id, "tech_reviewer": user_id}


def tech_verify_submission(submission_id, user_id, approve):
    """阶段④：经理指定的技术人员验证。通过 → 结算打款。"""
    conn = get_conn()
    sub, task = _get_sub_and_task(conn, submission_id)
    if not sub or not task:
        conn.close()
        return {"ok": False, "msg": "提交或任务不存在"}
    processed = _reject_if_processed(sub)
    if processed:
        conn.close()
        return processed
    if sub["stage"] != "manager_verified":
        conn.close()
        return {"ok": False, "msg": "当前不是待技术人员验证阶段"}
    if sub.get("tech_reviewer") and sub["tech_reviewer"] != user_id:
        conn.close()
        return {"ok": False, "msg": "你不是经理指定的技术人员"}
    if not approve:
        _reject_submission(conn, submission_id, sub["task_id"])
        conn.commit()
        conn.close()
        return {"ok": True, "stage": "rejected", "msg": "已打回"}
    # 定价：经理改过价用改价，否则 agreed_wage，再否则难度公式
    agent = conn.execute("SELECT * FROM agents WHERE id=?", (sub["agent_id"],)).fetchone()
    agent = dict(agent) if agent else None
    base = 0
    if agent:
        sal = conn.execute("SELECT base_salary FROM salaries WHERE user_id=?", (agent["user_id"],)).fetchone()
        base = sal["base_salary"] if sal else 0
    price = float(sub.get("price") or 0)
    if price <= 0:
        agreed = task.get("agreed_wage")
        if agreed is not None and float(agreed) > 0:
            price = round(float(agreed), 2)
        else:
            price = price_task(base, task.get("difficulty") or 0.5)
    conn.execute("UPDATE submissions SET status='approved', stage='verified', price=? WHERE id=?",
                 (price, submission_id))
    conn.execute("UPDATE agent_tasks SET status='done' WHERE id=?", (task["id"],))
    if agent:
        conn.execute(
            "INSERT INTO payouts (submission_id, user_id, agent_id, amount, status) "
            "VALUES (?,?,?,?,'pending') "
            "ON CONFLICT(submission_id) DO UPDATE SET amount=excluded.amount",
            (submission_id, agent["user_id"], agent["id"], price))
    # 外包任务验收通过 → 退回接单押金
    if task.get("outsource_accepter"):
        refund_outsource_deposit(task["id"], task["outsource_accepter"])
    conn.commit()
    conn.close()
    return {"ok": True, "stage": "verified", "price": price, "msg": f"验证通过，绩效标价 {price}"}


# ---------------------------------------------------------------------------
# 工资结算 / 打款
# ---------------------------------------------------------------------------
def get_payouts(status=None, company_id=None):
    """结算记录列表。可选 status 过滤（pending / paid），company_id 仅本公司。附员工姓名。"""
    conn = get_conn()
    sql = (
        "SELECT p.*, u.name AS user_name, t.title AS task_title "
        "FROM payouts p "
        "LEFT JOIN users u ON u.id = p.user_id "
        "LEFT JOIN agent_tasks t ON t.id = (SELECT task_id FROM submissions WHERE id=p.submission_id) "
    )
    conds, params = [], []
    if status:
        conds.append("p.status=?")
        params.append(status)
    if company_id:
        conds.append("u.company_id=?")
        params.append(company_id)
    if conds:
        sql += " WHERE " + " AND ".join(conds)
        rows = conn.execute(sql + " ORDER BY p.id DESC", tuple(params)).fetchall()
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
        "UPDATE payouts SET status='paid', paid_at=__NOW__ WHERE id=?",
        (payout_id,),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "msg": "已打款"}


def pay_all_payouts(company_id=None):
    """每月固定时间：把当月所有待打款一次性发放。company_id 提供时仅本公司。"""
    conn = get_conn()
    if company_id:
        pending_cond = ("status='pending' AND user_id IN "
                        "(SELECT id FROM users WHERE company_id=?)")
        n = conn.execute(
            "SELECT COUNT(*) AS c FROM payouts WHERE " + pending_cond, (company_id,)).fetchone()["c"]
        conn.execute("UPDATE payouts SET status='paid', paid_at=__NOW__ WHERE " + pending_cond,
                     (company_id,))
    else:
        n = conn.execute("SELECT COUNT(*) AS c FROM payouts WHERE status='pending'").fetchone()["c"]
        conn.execute("UPDATE payouts SET status='paid', paid_at=__NOW__ WHERE status='pending'")
    conn.commit()
    conn.close()
    return {"ok": True, "count": n, "msg": f"已发放 {n} 笔工资"}


def get_payout_stats(company_id=None):
    """结算概览：待打款金额与已打款总额。company_id 提供时仅本公司。"""
    conn = get_conn()
    if company_id:
        pending = conn.execute(
            "SELECT COALESCE(SUM(amount),0) AS s FROM payouts WHERE status='pending' "
            "AND user_id IN (SELECT id FROM users WHERE company_id=?)", (company_id,)).fetchone()["s"]
        paid = conn.execute(
            "SELECT COALESCE(SUM(amount),0) AS s FROM payouts WHERE status='paid' "
            "AND user_id IN (SELECT id FROM users WHERE company_id=?)", (company_id,)).fetchone()["s"]
    else:
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
    mid = insert_id(
        conn,
        "INSERT INTO agent_messages (from_agent, to_agent, content, priority) VALUES (?,?,?,?)",
        (from_agent, to_agent, content, priority),
    )
    conn.commit()
    conn.close()
    return {"id": mid, "from_agent": from_agent, "to_agent": to_agent,
            "content": content, "priority": priority}


# ---------------------------------------------------------------------------
# 查询工具（供 agent 使用）
# ---------------------------------------------------------------------------
# 只读工具允许访问的白名单表（业务表；绝不包含 users/sessions/sms_codes 等敏感表）
_ALLOWED_QUERY_TABLES = {
    "agents", "agent_tasks", "submissions", "agent_messages", "salaries",
    "payouts", "user_records", "work_records", "task_conditions",
    "notifications", "projects", "tasks",
}
_MAX_QUERY_ROWS = 200


def _extract_table_names(sql):
    """从 SELECT 语句里粗提取 FROM/JOIN 引用的表名（小写集合）。"""
    upper = sql.upper()
    names = set()
    for m in re.finditer(r"\b(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)\b", upper):
        names.add(m.group(1).lower())
    return names


def query_db(agent_id, sql):
    """只读查询数据库（仅允许 SELECT），供 query_db 工具使用。

    安全限制：仅 SELECT、禁危险关键字/注释/引号标识符、仅白名单表、强制 LIMIT。
    """
    sql = (sql or "").strip().rstrip(";")
    upper = sql.upper()
    if not upper.startswith("SELECT"):
        return {"error": "只允许 SELECT 查询"}
    # 危险关键字与注释/引号标识符：一律拒绝（防止绕过）
    for kw in (";", "DROP", "INSERT", "UPDATE", "DELETE", "ALTER", "CREATE",
               "ATTACH", "DETACH", "REPLACE", "EXEC", "PRAGMA", "UNION",
               "INTO", "COMMIT", "ROLLBACK", "--", "/*", "*/", '"', "`", "[", "]"):
        if kw in upper:
            return {"error": "仅允许只读 SELECT（拒绝危险片段）"}
    # 白名单表校验：FROM/JOIN 引用的表必须都在白名单内
    tables = _extract_table_names(sql)
    if not tables:
        return {"error": "查询必须 FROM 白名单表"}
    for t in tables:
        if t not in _ALLOWED_QUERY_TABLES:
            return {"error": f"禁止查询表 {t}"}
    if "LIMIT" not in upper:
        sql = sql + f" LIMIT {_MAX_QUERY_ROWS}"
    conn = get_conn()
    try:
        cur = conn.execute(sql)
        rows = cur.fetchmany(_MAX_QUERY_ROWS)
        data = [dict(r) for r in rows]
        cols = list(data[0].keys()) if data else []
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
        "query_secret_kb": {
            "name": "query_secret_kb",
            "description": (
                "检索本公司机密知识库（仅经理 Agent 可用）。访问受人工审批控制："
                "调用时必须说明 why(为什么需要)、usage(在项目里的用途)、danger(潜在危险)，"
                "提交后需经理批准，批准前不会返回任何机密内容。"
            ),
            "parameters": {"type": "object", "properties": {
                "query": {"type": "string", "description": "检索关键词"},
                "why": {"type": "string", "description": "为什么需要访问该机密内容"},
                "usage": {"type": "string", "description": "该机密内容在项目里的用途"},
                "danger": {"type": "string", "description": "使用该机密内容可能带来的潜在危险"}},
                "required": ["query", "why", "usage", "danger"]},
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
    if name == "query_secret_kb":
        # 机密知识库：仅经理 agent 可访问，且须经经理逐次审批
        if agent.get("role_type") != "manager":
            return {"error": "机密知识库仅经理 Agent 可访问"}
        company_id = _agent_company_id(agent)
        return access_secret_kb(
            agent["id"], company_id, args.get("query", ""),
            args.get("why", ""), args.get("usage", ""), args.get("danger", ""))
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
