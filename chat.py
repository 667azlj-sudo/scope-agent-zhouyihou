# -*- coding: utf-8 -*-
"""
chat.py —— 聊天 + 文件上传（内部协作）
员工私聊、老板员工群聊、负责人上传资料
"""
from dbcore import get_conn, insert_id, ensure_column


def init_chat_db():
    """建聊天和文件表"""
    conn = get_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS chats (
        id __PK__,
        type TEXT NOT NULL,                          -- 'direct'私聊 / 'group'群聊
        name TEXT,                                   -- 群聊名（私聊可空）
        created_at TEXT DEFAULT (__NOW__)
    );
    CREATE TABLE IF NOT EXISTS chat_members (
        id __PK__,
        chat_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS messages (
        id __PK__,
        chat_id INTEGER NOT NULL,
        sender_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        type TEXT DEFAULT 'text',
        lat REAL,
        lng REAL,
        status TEXT DEFAULT 'normal',
        created_at TEXT DEFAULT (__NOW__)
    );
    CREATE TABLE IF NOT EXISTS files (
        id __PK__,
        project_id INTEGER NOT NULL,
        filename TEXT NOT NULL,
        filepath TEXT NOT NULL,
        uploaded_by INTEGER NOT NULL,
        created_at TEXT DEFAULT (__NOW__)
    );
    CREATE TABLE IF NOT EXISTS friendships (
        id __PK__,
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

    CREATE TABLE IF NOT EXISTS group_invites (
        id __PK__,
        chat_id INTEGER NOT NULL,
        requester_id INTEGER NOT NULL,
        target_id INTEGER NOT NULL,
        target_approved INTEGER DEFAULT 0,
        manager_approved INTEGER DEFAULT 0,
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT (__NOW__)
    );
    """)
    # 兼容旧表：补 messages 新字段
    ensure_column(conn, "messages", "status", "TEXT DEFAULT 'normal'")
    ensure_column(conn, "messages", "type", "TEXT DEFAULT 'text'")
    ensure_column(conn, "messages", "lat", "REAL")
    ensure_column(conn, "messages", "lng", "REAL")
    # 兼容：chats 增加 company_id（总公司群用）
    ensure_column(conn, "chats", "company_id", "INTEGER")
    conn.commit()
    conn.close()


def create_chat(chat_type, name=None, member_ids=(1, 2)):
    """创建会话（direct私聊 / group群聊），并加入成员"""
    conn = get_conn()
    if chat_type == "group" and not name:
        name = "群聊"
    chat_id = insert_id(
        conn,
        "INSERT INTO chats (type, name) VALUES (?,?)", (chat_type, name))
    for uid in member_ids:
        conn.execute("INSERT INTO chat_members (chat_id, user_id) VALUES (?,?)",
                     (chat_id, uid))
    conn.commit()
    conn.close()
    return chat_id


def create_company_chat(company_id, name="总公司群"):
    """创建公司唯一的基础群聊（type='company'），返回 chat_id。"""
    conn = get_conn()
    chat_id = insert_id(
        conn,
        "INSERT INTO chats (type, name, company_id) VALUES ('company', ?, ?)", (name, company_id))
    conn.commit()
    conn.close()
    return chat_id


def get_company_chat(company_id):
    """查公司的总公司群，返回 dict 或 None。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM chats WHERE type='company' AND company_id=?", (company_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def add_chat_member(chat_id, user_id):
    """把某人拉进群聊（经理强拉人）。已存在则忽略。"""
    conn = get_conn()
    exists = conn.execute(
        "SELECT id FROM chat_members WHERE chat_id=? AND user_id=?", (chat_id, user_id)).fetchone()
    if not exists:
        conn.execute("INSERT INTO chat_members (chat_id, user_id) VALUES (?,?)", (chat_id, user_id))
        conn.commit()
    conn.close()
    return {"ok": True}


def get_chat_members(chat_id):
    """群聊成员列表（含名字/岗位）。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT u.id, u.name, u.role, u.position FROM chat_members cm "
        "JOIN users u ON u.id = cm.user_id WHERE cm.chat_id=? ORDER BY u.id",
        (chat_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_chat_info(chat_id):
    """单个会话信息。"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM chats WHERE id=?", (chat_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def is_chat_member(chat_id, user_id):
    """判断某人是否已在群里。"""
    conn = get_conn()
    row = conn.execute("SELECT id FROM chat_members WHERE chat_id=? AND user_id=?",
                       (chat_id, user_id)).fetchone()
    conn.close()
    return row is not None


# ---------------------------------------------------------------------------
# 加群申请（员工加人需对方 + 经理双审；经理拉人则直接加）
# ---------------------------------------------------------------------------
def create_group_invite(chat_id, requester_id, target_id):
    """发起加群申请。目标已在群里或已有待处理申请则拒绝。"""
    if is_chat_member(chat_id, target_id):
        return {"ok": False, "msg": "对方已在群里"}
    conn = get_conn()
    dup = conn.execute(
        "SELECT id FROM group_invites WHERE chat_id=? AND target_id=? AND status='pending'",
        (chat_id, target_id)).fetchone()
    if dup:
        conn.close()
        return {"ok": False, "msg": "已有待处理的申请"}
    gid = insert_id(
        conn,
        "INSERT INTO group_invites (chat_id, requester_id, target_id) VALUES (?,?,?)",
        (chat_id, requester_id, target_id))
    conn.commit()
    conn.close()
    return {"ok": True, "id": gid}


def _invite_with_names(conn, invite_id):
    row = conn.execute(
        "SELECT i.*, u.name AS target_name, r.name AS requester_name, c.name AS chat_name "
        "FROM group_invites i "
        "JOIN users u ON u.id=i.target_id "
        "JOIN users r ON r.id=i.requester_id "
        "LEFT JOIN chats c ON c.id=i.chat_id "
        "WHERE i.id=?", (invite_id,)).fetchone()
    return dict(row) if row else None


def get_invites_for_target(user_id):
    """被加的人：待我审核的申请（我还没表态的）。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT i.*, r.name AS requester_name, c.name AS chat_name "
        "FROM group_invites i JOIN users r ON r.id=i.requester_id "
        "LEFT JOIN chats c ON c.id=i.chat_id "
        "WHERE i.target_id=? AND i.status='pending' AND i.target_approved=0 "
        "ORDER BY i.id DESC", (user_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_pending_invites_for_manager():
    """经理：待我审核的申请（还没审批的）。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT i.*, u.name AS target_name, r.name AS requester_name, c.name AS chat_name "
        "FROM group_invites i JOIN users u ON u.id=i.target_id "
        "JOIN users r ON r.id=i.requester_id "
        "LEFT JOIN chats c ON c.id=i.chat_id "
        "WHERE i.status='pending' AND i.manager_approved=0 "
        "ORDER BY i.id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def respond_group_invite(invite_id, user_id, approve, role):
    """对方 / 经理审核加群申请。两方都同意则真正入群。"""
    conn = get_conn()
    inv = conn.execute("SELECT * FROM group_invites WHERE id=?", (invite_id,)).fetchone()
    if not inv or inv["status"] != "pending":
        conn.close()
        return {"ok": False, "msg": "申请不存在或已处理"}
    inv = dict(inv)
    if role == "manager":
        conn.execute("UPDATE group_invites SET manager_approved=? WHERE id=?",
                     (1 if approve else 0, invite_id))
    else:
        if inv["target_id"] != user_id:
            conn.close()
            return {"ok": False, "msg": "无权处理该申请"}
        conn.execute("UPDATE group_invites SET target_approved=? WHERE id=?",
                     (1 if approve else 0, invite_id))
    conn.commit()

    inv2 = dict(conn.execute("SELECT * FROM group_invites WHERE id=?", (invite_id,)).fetchone())
    if not approve:
        conn.execute("UPDATE group_invites SET status='rejected' WHERE id=?", (invite_id,))
        conn.commit()
        conn.close()
        return {"ok": True, "msg": "已拒绝"}
    if inv2["target_approved"] and inv2["manager_approved"]:
        add_chat_member(inv2["chat_id"], inv2["target_id"])
        conn.execute("UPDATE group_invites SET status='approved' WHERE id=?", (invite_id,))
        conn.commit()
        conn.close()
        return {"ok": True, "msg": "已同意并加入群聊"}
    conn.close()
    return {"ok": True, "msg": "已记录，等待另一方审核"}


def send_message(chat_id, sender_id, content, msg_type="text", lat=None, lng=None):
    """发消息（支持 text / location）"""
    conn = get_conn()
    conn.execute(
        "INSERT INTO messages (chat_id, sender_id, content, type, lat, lng) VALUES (?,?,?,?,?,?)",
        (chat_id, sender_id, content, msg_type, lat, lng))
    conn.commit()
    conn.close()


def _minutes_since(created_at):
    """计算某时间戳距现在的分钟数（跨后端，纯 Python）。"""
    try:
        from datetime import datetime
        dt = datetime.strptime(str(created_at), "%Y-%m-%d %H:%M:%S")
        return (datetime.now() - dt).total_seconds() / 60
    except Exception:  # noqa: BLE001
        return 0


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
    if _minutes_since(row["created_at"]) > 120:
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


def get_user_sent_messages(user_id, limit=30):
    """某用户最近发过的文字消息（聊天记录，可导入为工作记录）。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT content, created_at FROM messages "
        "WHERE sender_id=? AND type='text' AND status='normal' "
        "ORDER BY id DESC LIMIT ?", (user_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def upload_file(project_id, filename, filepath, uploaded_by):
    """负责人上传资料，返回文件 id"""
    conn = get_conn()
    file_id = insert_id(
        conn,
        "INSERT INTO files (project_id, filename, filepath, uploaded_by) VALUES (?,?,?,?)",
        (project_id, filename, filepath, uploaded_by))
    conn.commit()
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
        "SELECT u.id, u.name, u.role, u.position FROM friendships f JOIN users u "
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
    """当前用户的会话列表（含最新消息、真正的未读计数）。有未读的会话置顶，其余按最新消息排序。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT c.id, c.type, c.name, "
        "(SELECT content FROM messages m WHERE m.chat_id=c.id ORDER BY m.id DESC LIMIT 1) AS last_msg, "
        "(SELECT COALESCE(MAX(id),0) FROM messages m WHERE m.chat_id=c.id) AS last_msg_id, "
        "(SELECT COUNT(*) FROM messages m WHERE m.chat_id=c.id AND m.status='normal' "
        " AND m.sender_id!=? AND m.id > COALESCE("
        "   (SELECT last_read_id FROM chat_reads r WHERE r.chat_id=c.id AND r.user_id=?), 0)"
        ") AS unread "
        "FROM chats c JOIN chat_members cm ON c.id=cm.chat_id "
        "WHERE cm.user_id=? "
        "ORDER BY (unread > 0) DESC, last_msg_id DESC",
        (user_id, user_id, user_id)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
