# -*- coding: utf-8 -*-
"""
chat.py —— 聊天 + 文件上传（内部协作）
员工私聊、老板员工群聊、负责人上传资料
"""
import sqlite3

DB_PATH = "scope_agent.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_chat_db():
    """建聊天和文件表"""
    conn = get_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS chats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT NOT NULL,                          -- 'direct'私聊 / 'group'群聊
        name TEXT,                                   -- 群聊名（私聊可空）
        created_at TEXT DEFAULT (datetime('now', 'localtime'))
    );
    CREATE TABLE IF NOT EXISTS chat_members (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id INTEGER NOT NULL,
        sender_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        type TEXT DEFAULT 'text',
        lat REAL,
        lng REAL,
        status TEXT DEFAULT 'normal',
        created_at TEXT DEFAULT (datetime('now', 'localtime'))
    );
    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        filename TEXT NOT NULL,
        filepath TEXT NOT NULL,
        uploaded_by INTEGER NOT NULL,
        created_at TEXT DEFAULT (datetime('now', 'localtime'))
    );
    CREATE TABLE IF NOT EXISTS friendships (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        friend_id INTEGER NOT NULL,
        status TEXT DEFAULT 'approved'
    );
    CREATE TABLE IF NOT EXISTS chat_reads (
        chat_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        last_read_id INTEGER DEFAULT 0,
        PRIMARY KEY (chat_id, user_id)
    );
    """)
    # 兼容旧表：补 messages 新字段
    mcols = [r["name"] for r in conn.execute("PRAGMA table_info(messages)").fetchall()]
    if "status" not in mcols:
        conn.execute("ALTER TABLE messages ADD COLUMN status TEXT DEFAULT 'normal'")
    if "type" not in mcols:
        conn.execute("ALTER TABLE messages ADD COLUMN type TEXT DEFAULT 'text'")
    if "lat" not in mcols:
        conn.execute("ALTER TABLE messages ADD COLUMN lat REAL")
    if "lng" not in mcols:
        conn.execute("ALTER TABLE messages ADD COLUMN lng REAL")
    conn.commit()
    conn.close()


def create_chat(chat_type, name=None, member_ids=(1, 2)):
    """创建会话（direct私聊 / group群聊），并加入成员"""
    conn = get_conn()
    if chat_type == "group" and not name:
        name = "群聊"
    cur = conn.execute(
        "INSERT INTO chats (type, name) VALUES (?,?)", (chat_type, name))
    chat_id = cur.lastrowid
    for uid in member_ids:
        conn.execute("INSERT INTO chat_members (chat_id, user_id) VALUES (?,?)",
                     (chat_id, uid))
    conn.commit()
    conn.close()
    return chat_id


def send_message(chat_id, sender_id, content, msg_type="text", lat=None, lng=None):
    """发消息（支持 text / location）"""
    conn = get_conn()
    conn.execute(
        "INSERT INTO messages (chat_id, sender_id, content, type, lat, lng) VALUES (?,?,?,?,?,?)",
        (chat_id, sender_id, content, msg_type, lat, lng))
    conn.commit()
    conn.close()


def withdraw_message(mid, user_id):
    """撤回消息（2分钟内、只能撤回自己的）"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM messages WHERE id=?", (mid,)).fetchone()
    if not row:
        conn.close()
        return False, "消息不存在"
    if row["sender_id"] != user_id:
        conn.close()
        return False, "只能撤回自己的消息"
    mins = conn.execute(
        "SELECT (julianday('now','localtime') - julianday(?)) * 24 * 60 AS m",
        (row["created_at"],)).fetchone()["m"]
    if mins > 120:
        conn.close()
        return False, "超过2分钟，不能撤回"
    conn.execute("UPDATE messages SET status='withdrawn' WHERE id=?", (mid,))
    conn.commit()
    conn.close()
    return True, "已撤回"


def get_messages(chat_id):
    """获取会话的所有消息（含发送者名字）"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT m.*, u.name AS sender_name FROM messages m "
        "JOIN users u ON m.sender_id=u.id WHERE m.chat_id=? ORDER BY m.id",
        (chat_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def upload_file(project_id, filename, filepath, uploaded_by):
    """负责人上传资料，返回文件 id"""
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO files (project_id, filename, filepath, uploaded_by) VALUES (?,?,?,?)",
        (project_id, filename, filepath, uploaded_by))
    conn.commit()
    file_id = cur.lastrowid
    conn.close()
    return file_id


def add_friend(requester_id, target_id, requester_role, target_role):
    """加好友：负责人参与时直接通过；员工之间需负责人审核"""
    if requester_role == "manager" or target_role == "manager":
        status = "approved"
    else:
        status = "pending"
    conn = get_conn()
    conn.execute("INSERT INTO friendships (user_id, friend_id, status) VALUES (?,?,?)",
                 (requester_id, target_id, status))
    conn.commit()
    conn.close()
    return status


def pending_friendships():
    """查所有待审核的好友申请（负责人可审核）"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT f.id, f.user_id, u.name FROM friendships f "
        "JOIN users u ON f.user_id=u.id WHERE f.status='pending'").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def approve_friend(friend_id, approve, approver_role):
    """负责人审核好友申请"""
    if approver_role != "manager":
        return False, "权限不足：只有负责人能审核"
    new_status = "approved" if approve else "rejected"
    conn = get_conn()
    conn.execute("UPDATE friendships SET status=? WHERE id=?", (new_status, friend_id))
    conn.commit()
    conn.close()
    return True, "已通过" if approve else "已拒绝"


def is_friend(user_id, other_id):
    """判断两人是否为好友（双向、已通过）"""
    conn = get_conn()
    row = conn.execute(
        "SELECT id FROM friendships WHERE status='approved' AND "
        "(user_id=? AND friend_id=? OR user_id=? AND friend_id=?)",
        (user_id, other_id, other_id, user_id)).fetchone()
    conn.close()
    return row is not None


def get_friends(user_id):
    """查某人的好友列表"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT u.id, u.name, u.role FROM friendships f JOIN users u "
        "ON u.id = CASE WHEN f.user_id=? THEN f.friend_id ELSE f.user_id END "
        "WHERE (f.user_id=? OR f.friend_id=?) AND f.status='approved'",
        (user_id, user_id, user_id)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_read(chat_id, user_id):
    """标记某会话对某用户已读（把 last_read_id 设为最新一条消息 id）"""
    conn = get_conn()
    last = conn.execute(
        "SELECT COALESCE(MAX(id),0) AS m FROM messages WHERE chat_id=?", (chat_id,)).fetchone()["m"]
    conn.execute(
        "INSERT INTO chat_reads (chat_id, user_id, last_read_id) VALUES (?,?,?) "
        "ON CONFLICT(chat_id, user_id) DO UPDATE SET last_read_id=excluded.last_read_id",
        (chat_id, user_id, last))
    conn.commit()
    conn.close()


def get_user_chats(user_id):
    """当前用户的会话列表（含最新消息、真正的未读计数）"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT c.id, c.type, c.name, "
        "(SELECT content FROM messages m WHERE m.chat_id=c.id ORDER BY m.id DESC LIMIT 1) AS last_msg, "
        "(SELECT COUNT(*) FROM messages m WHERE m.chat_id=c.id AND m.status='normal' "
        " AND m.sender_id!=? AND m.id > COALESCE("
        "   (SELECT last_read_id FROM chat_reads r WHERE r.chat_id=c.id AND r.user_id=?), 0)"
        ") AS unread "
        "FROM chats c JOIN chat_members cm ON c.id=cm.chat_id "
        "WHERE cm.user_id=? ORDER BY c.id DESC",
        (user_id, user_id, user_id)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
