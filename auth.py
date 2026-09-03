# -*- coding: utf-8 -*-
"""
auth.py —— 权限审批流
负责人拥有确认/审批权；员工可协商，变更需负责人批准
"""
import hashlib
import secrets
import sqlite3

DB_PATH = "scope_agent.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_users():
    """建 users 和 sessions 表，并兼容旧表（补 password_hash 列）"""
    conn = get_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        role TEXT NOT NULL,
        password_hash TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        token TEXT NOT NULL,
        user_id INTEGER NOT NULL
    );
    """)
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "password_hash" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN password_hash TEXT DEFAULT ''")
    if "memory" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN memory TEXT DEFAULT '{}'")
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


def get_all_users():
    """查所有用户，返回 [dict, ...]"""
    conn = get_conn()
    rows = conn.execute("SELECT * FROM users").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def hash_password(password):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), b"scope_agent_salt", 100000).hex()


def verify_password(password, password_hash):
    return hash_password(password) == password_hash


def register(name, password, role):
    """注册用户（role 必填，必须是 user/employee/manager）"""
    if role not in ("user", "employee", "manager"):
        return False, "角色无效，请选择岗位"
    conn = get_conn()
    try:
        conn.execute("INSERT INTO users (name, role, password_hash) VALUES (?,?,?)",
                     (name, role, hash_password(password)))
        conn.commit()
        return True, "注册成功"
    except sqlite3.IntegrityError:
        return False, "用户名已存在"
    finally:
        conn.close()


def login(name, password):
    """登录，验证密码，生成 token；返回 (token, user) 或 (None, msg)"""
    user = get_user(name)
    if not user or not verify_password(password, user.get("password_hash", "")):
        return None, "用户名或密码错误"
    token = secrets.token_hex(32)
    conn = get_conn()
    conn.execute("INSERT INTO sessions (token, user_id) VALUES (?,?)", (token, user["id"]))
    conn.commit()
    conn.close()
    return token, user


def get_user_by_token(token):
    """根据 token 查用户"""
    conn = get_conn()
    row = conn.execute(
        "SELECT u.* FROM users u JOIN sessions s ON u.id=s.user_id WHERE s.token=?",
        (token,)).fetchone()
    conn.close()
    return dict(row) if row else None


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
