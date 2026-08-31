# -*- coding: utf-8 -*-
"""
db.py —— 数据持久化（SQLite）
存储项目和事项，支持查询
"""
import sqlite3

DB_PATH = "scope_agent.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row   # 让查询结果能按列名访问
    return conn


def init_db():
    """建两张表：projects（项目）+ tasks（事项）"""
    conn = get_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now', 'localtime'))
    );
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        type TEXT NOT NULL,
        suggestion TEXT DEFAULT '',
        status TEXT DEFAULT 'pending_review',
        FOREIGN KEY (project_id) REFERENCES projects(id)
    );
    """)
    conn.commit()
    conn.close()


def save_project(name):
    """存一个项目，返回它的 id"""
    conn = get_conn()
    cur = conn.execute("INSERT INTO projects (name) VALUES (?)", (name,))
    conn.commit()
    pid = cur.lastrowid
    conn.close()
    return pid


def save_tasks(project_id, simple, fuzzy):
    """存事项：simple 状态=auto_assigned，fuzzy 状态=pending_review"""
    conn = get_conn()
    for it in simple:
        conn.execute(
            "INSERT INTO tasks (project_id, content, type, suggestion, status) VALUES (?,?,?,?,?)",
            (project_id, it["task"], it["type"], it.get("suggestion", ""), "auto_assigned"),
        )
    for it in fuzzy:
        conn.execute(
            "INSERT INTO tasks (project_id, content, type, suggestion, status) VALUES (?,?,?,?,?)",
            (project_id, it["task"], it["type"], it.get("suggestion", ""), "pending_review"),
        )
    conn.commit()
    conn.close()


def query_tasks(project_id, status=None):
    """查项目的事项，可按状态过滤"""
    conn = get_conn()
    if status:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE project_id=? AND status=?", (project_id, status)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE project_id=?", (project_id,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    from splitter import split_project
    from router import route

    init_db()                                   # 1. 建表
    desc = "开发一个电商小程序"
    tasks_json = split_project(desc)            # 2. 拆解
    simple, fuzzy = route(tasks_json)           # 3. 路由
    pid = save_project(desc)                    # 4. 存项目
    save_tasks(pid, simple, fuzzy)              # 5. 存事项
    print(f"项目已入库，id={pid}")

    auto = query_tasks(pid, "auto_assigned")    # 6. 查"自动分配"的
    pending = query_tasks(pid, "pending_review")# 7. 查"待确认"的
    print(f"自动分配 {len(auto)} 个，待确认 {len(pending)} 个")
    print("\n待确认事项（存在数据库里了）：")
    for t in pending:
        print(f"  [{t['id']}] {t['content']}")
