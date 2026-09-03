# -*- coding: utf-8 -*-
"""
company.py —— 公司 / 邀请码

经理注册时创建公司并生成邀请码；员工凭邀请码加入公司。
"""
import secrets
import sqlite3
import string

DB_PATH = "scope_agent.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _gen_code():
    """8 位大写字母+数字邀请码，去掉易混字符"""
    alphabet = string.ascii_uppercase + string.digits
    alphabet = alphabet.replace("O", "").replace("0", "").replace("I", "").replace("1", "")
    return "".join(secrets.choice(alphabet) for _ in range(8))


def init_company_db():
    conn = get_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS companies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        invite_code TEXT NOT NULL UNIQUE,
        manager_id INTEGER,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    );
    """)
    conn.commit()
    conn.close()


def create_company(name, manager_id):
    """经理创建公司，返回公司 dict。同名公司已存在则报错。"""
    conn = get_conn()
    try:
        code = _gen_code()
        cur = conn.execute(
            "INSERT INTO companies (name, invite_code, manager_id) VALUES (?,?,?)",
            (name, code, manager_id),
        )
        conn.commit()
        cid = cur.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        return None, "公司名已存在"
    conn.close()
    return {"id": cid, "name": name, "invite_code": code}, None


def get_company(company_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM companies WHERE id=?", (company_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_company_by_code(code):
    """按邀请码查公司"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM companies WHERE invite_code=?", (code.strip().upper(),)).fetchone()
    conn.close()
    return dict(row) if row else None


def set_manager(company_id, manager_id):
    """回填公司的负责人用户 id"""
    conn = get_conn()
    conn.execute("UPDATE companies SET manager_id=? WHERE id=?", (manager_id, company_id))
    conn.commit()
    conn.close()


def list_companies():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM companies ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_company_members(company_id):
    """某公司的成员（用户）列表"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, name, role, position FROM users WHERE company_id=? ORDER BY id",
        (company_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
