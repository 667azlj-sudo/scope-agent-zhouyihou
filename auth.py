# -*- coding: utf-8 -*-
"""
auth.py —— 权限审批流 + 注册登录鉴权
负责人拥有确认/审批权；员工可协商，变更需负责人批准
"""
import hashlib
import os
import secrets
import time

from dbcore import get_conn, ensure_column, is_pg, IntegrityErrors

# 验证码有效期（秒）
SMS_CODE_TTL = 300

# 会话有效期（秒）。默认 7 天，可用环境变量 SESSION_TTL_HOURS 覆盖。
SESSION_TTL_SECONDS = int(os.environ.get("SESSION_TTL_HOURS", "168") or "168") * 3600

# 验证码重发间隔（秒）。同一手机号在该间隔内不允许重复发送。
SMS_RESEND_SECONDS = int(os.environ.get("SMS_RESEND_SECONDS", "60") or "60")

# 密码哈希迭代次数
PBKDF2_ITERATIONS = 100000


def init_users():
    """建 users / sessions / sms_codes 表，并兼容旧表（补列）"""
    conn = get_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id __PK__,
        name TEXT NOT NULL UNIQUE,
        role TEXT NOT NULL,
        password_hash TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS sessions (
        id __PK__,
        token TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        expires_at INTEGER
    );
    CREATE TABLE IF NOT EXISTS sms_codes (
        phone TEXT PRIMARY KEY,
        code TEXT NOT NULL,
        expires_at INTEGER NOT NULL
    );
    """)
    ensure_column(conn, "users", "password_hash", "TEXT DEFAULT ''")
    ensure_column(conn, "users", "memory", "TEXT DEFAULT '{}'")
    ensure_column(conn, "users", "phone", "TEXT")
    ensure_column(conn, "users", "company_id", "INTEGER")
    ensure_column(conn, "users", "position", "TEXT")
    # 迁移：sessions 增加 expires_at（token 过期）
    ensure_column(conn, "sessions", "expires_at", "INTEGER")
    # phone 唯一索引（幂等）
    try:
        if is_pg():
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone ON users(phone)")
        else:
            conn.execute("CREATE UNIQUE INDEX idx_users_phone ON users(phone)")
    except Exception:  # noqa: BLE001
        pass
    conn.commit()
    conn.close()


def add_user(name, role):
    """加用户，role = 'manager'(负责人) 或 'employee'(员工)"""
    conn = get_conn()
    conn.execute("INSERT INTO users (name, role) VALUES (?,?)", (name, role))
    conn.commit()
    conn.close()


def get_user(name):
    """按名字查用户，返回 dict 或 None"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE name=?", (name,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(uid):
    """按 id 查用户，返回 dict 或 None"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_phone(phone):
    """按手机号查用户，返回 dict 或 None"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE phone=?", (phone,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_users():
    """查所有用户，返回 [dict, ...]"""
    conn = get_conn()
    rows = conn.execute("SELECT * FROM users").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def hash_password(password, salt=None):
    """PBKDF2-SHA256 随机盐哈希。返回格式 pbkdf2_sha256$迭代$盐$哈希。

    每个用户使用独立随机盐，避免彩虹表攻击。
    """
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256", (password or "").encode(), salt.encode(), PBKDF2_ITERATIONS
    ).hex()
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${dk}"


def verify_password(password, password_hash):
    """校验密码。兼容旧版固定盐格式（裸 hex，不含 $）。"""
    ph = password_hash or ""
    if not ph:
        return False
    if "$" not in ph:
        # 旧格式：固定盐 scope_agent_salt，仅作平滑迁移用
        legacy = hashlib.pbkdf2_hmac(
            "sha256", (password or "").encode(), b"scope_agent_salt", 100000
        ).hex()
        return ph == legacy
    try:
        algo, iters, salt, dk = ph.split("$")
        if algo != "pbkdf2_sha256":
            return False
        calc = hashlib.pbkdf2_hmac(
            "sha256", (password or "").encode(), salt.encode(), int(iters)
        ).hex()
        return calc == dk
    except (ValueError, TypeError):
        return False


def _normalize_phone(phone):
    """校验并归一化大陆手机号，返回 11 位数字或 None"""
    p = str(phone or "").strip()
    if p.startswith("+86"):
        p = p[3:]
    if len(p) != 11 or not p.isdigit() or not p.startswith("1"):
        return None
    return p


def can_send_code(phone):
    """防刷：返回 (ok, msg)。同一手机号在 SMS_RESEND_SECONDS 内不允许重复发送。"""
    conn = get_conn()
    row = conn.execute("SELECT expires_at FROM sms_codes WHERE phone=?", (phone,)).fetchone()
    conn.close()
    if row and row["expires_at"]:
        remaining = int(row["expires_at"]) - int(time.time())
        # 距上次发送不足 SMS_RESEND_SECONDS 时拒绝
        if remaining > SMS_CODE_TTL - SMS_RESEND_SECONDS:
            return False, "请勿频繁发送验证码，稍后再试"
    return True, ""


def create_verify_code(phone):
    """生成 6 位验证码并入库，返回验证码（由调用方发送短信）。"""
    code = f"{secrets.randbelow(1000000):06d}"
    conn = get_conn()
    conn.execute(
        "INSERT INTO sms_codes (phone, code, expires_at) VALUES (?,?,?) "
        "ON CONFLICT(phone) DO UPDATE SET code=excluded.code, expires_at=excluded.expires_at",
        (phone, code, int(time.time()) + SMS_CODE_TTL),
    )
    conn.commit()
    conn.close()
    return code


def verify_code(phone, code):
    """校验验证码，成功后删除该条记录。返回 (ok, msg)。"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM sms_codes WHERE phone=?", (phone,)).fetchone()
    if not row:
        conn.close()
        return False, "请先获取验证码"
    row = dict(row)
    if int(time.time()) > row["expires_at"]:
        conn.execute("DELETE FROM sms_codes WHERE phone=?", (phone,))
        conn.commit()
        conn.close()
        return False, "验证码已过期"
    if row["code"] != str(code or "").strip():
        conn.close()
        return False, "验证码错误"
    conn.execute("DELETE FROM sms_codes WHERE phone=?", (phone,))
    conn.commit()
    conn.close()
    return True, "验证通过"


def register(name, password, role, phone=None, company_id=None, position=None):
    """注册用户（role 必填；phone 可选；company_id/position 为公司归属与岗位）"""
    if role not in ("user", "employee", "manager"):
        return False, "角色无效，请选择岗位"
    phone = _normalize_phone(phone) if phone else None
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO users (name, role, password_hash, phone, company_id, position) "
            "VALUES (?,?,?,?,?,?)",
            (name, role, hash_password(password), phone, company_id, position),
        )
        conn.commit()
        return True, "注册成功"
    except IntegrityErrors:
        return False, "用户名或手机号已存在"
    finally:
        conn.close()


def login(account, password):
    """登录（account 可以是用户名或手机号），验证密码，生成 token。

    返回 (token, user) 或 (None, msg)。
    """
    user = get_user(account)
    if not user:
        phone = _normalize_phone(account)
        if phone:
            user = get_user_by_phone(phone)
    if not user or not verify_password(password, user.get("password_hash", "")):
        return None, "用户名或密码错误"
    token = secrets.token_hex(32)
    expires = int(time.time()) + SESSION_TTL_SECONDS
    conn = get_conn()
    conn.execute(
        "INSERT INTO sessions (token, user_id, expires_at) VALUES (?,?,?)",
        (token, user["id"], expires),
    )
    conn.commit()
    conn.close()
    return token, user


def get_user_by_token(token):
    """根据 token 查用户（已过期则删除该会话并返回 None）"""
    if not token:
        return None
    conn = get_conn()
    row = conn.execute(
        "SELECT u.*, s.expires_at AS _expires_at FROM users u "
        "JOIN sessions s ON u.id=s.user_id WHERE s.token=?",
        (token,),
    ).fetchone()
    if not row:
        conn.close()
        return None
    row = dict(row)
    expires_at = row.pop("_expires_at", None)
    if expires_at is not None and int(time.time()) > expires_at:
        conn.execute("DELETE FROM sessions WHERE token=?", (token,))
        conn.commit()
        conn.close()
        return None
    conn.close()
    return row


def logout(token):
    """删除会话，使 token 失效。"""
    conn = get_conn()
    conn.execute("DELETE FROM sessions WHERE token=?", (token or "",))
    conn.commit()
    conn.close()
    return True


def parse_bearer(header):
    """从 Authorization 头解析 Bearer token；无效返回空串。"""
    h = (header or "").strip()
    if h.lower().startswith("bearer "):
        return h[7:].strip()
    return ""


def confirm_task(task_id, user_name):
    """负责人确认事项：pending_review → assigned（只有 manager 能做）"""
    user = get_user(user_name)
    if not user or user["role"] != "manager":
        return False, "❌ 权限不足：只有负责人能确认事项"
    conn = get_conn()
    conn.execute("UPDATE tasks SET status='assigned' WHERE id=?", (task_id,))
    conn.commit()
    conn.close()
    return True, f"✅ 事项 {task_id} 已确认并分配"


def propose_change(task_id, user_name, new_content):
    """员工协商：assigned → negotiating，记录协商的新内容"""
    user = get_user(user_name)
    if not user:
        return False, "❌ 用户不存在"
    conn = get_conn()
    conn.execute(
        "UPDATE tasks SET status='negotiating', suggestion=? WHERE id=?",
        (new_content, task_id),
    )
    conn.commit()
    conn.close()
    return True, f"✅ 事项 {task_id} 已提交协商，等负责人审批"


def approve_change(task_id, user_name, approve):
    """负责人审批协商：negotiating → approved/rejected（只有 manager 能做）"""
    user = get_user(user_name)
    if not user or user["role"] != "manager":
        return False, "❌ 权限不足：只有负责人能审批"
    new_status = "approved" if approve else "rejected"
    conn = get_conn()
    conn.execute("UPDATE tasks SET status=? WHERE id=?", (new_status, task_id))
    conn.commit()
    conn.close()
    return True, f"✅ 事项 {task_id} 已{'批准' if approve else '驳回'}"


if __name__ == "__main__":
    from db import query_tasks

    init_users()
    # 建两个用户：一个负责人，一个员工
    add_user("张总", "manager")
    add_user("小李", "employee")

    # 先看有哪些待确认事项（假设 db.py 已跑过，数据库里有数据）
    print("===== 权限审批流 =====\n")

    # 1. 员工试图确认事项（应该被拒绝！）
    ok, msg = confirm_task(9, "小李")
    print(f"1. 员工小李确认事项9 → {msg}")

    # 2. 负责人确认事项（应该成功）
    ok, msg = confirm_task(9, "张总")
    print(f"2. 负责人张总确认事项9 → {msg}")

    # 3. 员工协商（提出变更）
    ok, msg = propose_change(9, "小李", "建议：数据库设计改为由第三方托管")
    print(f"3. 员工小李协商事项9 → {msg}")

    # 4. 员工试图审批自己的协商（应该被拒绝！）
    ok, msg = approve_change(9, "小李", True)
    print(f"4. 员工小李审批 → {msg}")

    # 5. 负责人审批通过（应该成功）
    ok, msg = approve_change(9, "张总", True)
    print(f"5. 负责人张总审批 → {msg}")
