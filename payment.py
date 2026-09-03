# -*- coding: utf-8 -*-
"""
payment.py —— SaaS 套餐 / 订单 / 订阅

对外收费（方案一 SaaS）：企业负责人购买套餐，按套餐解锁 Agent 数量与有效期。

支付网关：当前为「本地模拟」。`pay_order()` 直接模拟支付成功，并把订单置为
paid、订阅生效/续期。后续接入微信支付 / 支付宝时，只需在 `pay_order()` 里
换成「创建支付单 + 异步回调验签」即可，订单/订阅的表结构和前端无需改动。
"""
import sqlite3
import time
import uuid
from datetime import datetime, timedelta

DB_PATH = "scope_agent.db"

# 内置套餐（价格：元）
DEFAULT_PLANS = [
    {"name": "免费版", "price": 0, "duration_days": 0, "agent_limit": 1,
     "description": "试用，1 个 Agent"},
    {"name": "基础版", "price": 99, "duration_days": 30, "agent_limit": 5,
     "description": "小团队，5 个 Agent"},
    {"name": "企业版", "price": 299, "duration_days": 90, "agent_limit": 20,
     "description": "成长团队，20 个 Agent"},
    {"name": "旗舰版", "price": 999, "duration_days": 365, "agent_limit": 100,
     "description": "大型企业，100 个 Agent"},
]


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_payment_db():
    """建 plans / orders / subscriptions 表并写入内置套餐。"""
    conn = get_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        price REAL DEFAULT 0,
        duration_days INTEGER DEFAULT 0,
        agent_limit INTEGER DEFAULT 1,
        description TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_no TEXT NOT NULL UNIQUE,
        user_id INTEGER NOT NULL,
        plan_id INTEGER NOT NULL,
        amount REAL DEFAULT 0,
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT (datetime('now','localtime')),
        paid_at TEXT
    );
    CREATE TABLE IF NOT EXISTS subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL UNIQUE,
        plan_id INTEGER NOT NULL,
        status TEXT DEFAULT 'active',
        started_at TEXT,
        expires_at TEXT
    );
    """)
    if conn.execute("SELECT COUNT(*) AS c FROM plans").fetchone()["c"] == 0:
        for p in DEFAULT_PLANS:
            conn.execute(
                "INSERT INTO plans (name, price, duration_days, agent_limit, description) "
                "VALUES (?,?,?,?,?)",
                (p["name"], p["price"], p["duration_days"], p["agent_limit"], p["description"]),
            )
    conn.commit()
    conn.close()


def get_plans():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM plans ORDER BY price").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_plan(plan_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM plans WHERE id=?", (plan_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_order(user_id, plan_id):
    """创建待支付订单。返回订单 dict。"""
    plan = get_plan(plan_id)
    if not plan:
        return {"ok": False, "msg": "套餐不存在"}
    order_no = f"SO{time.strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:6].upper()}"
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO orders (order_no, user_id, plan_id, amount, status) VALUES (?,?,?,?,'pending')",
        (order_no, user_id, plan_id, plan["price"]),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "order_no": order_no, "amount": plan["price"],
            "plan_name": plan["name"], "id": cur.lastrowid}


def pay_order(order_no):
    """模拟支付成功：订单 → paid，并开通/续期订阅。

    接入真实支付时，这里替换为「验证回调签名 → 再执行以下逻辑」。
    """
    conn = get_conn()
    order = conn.execute("SELECT * FROM orders WHERE order_no=?", (order_no,)).fetchone()
    if not order:
        conn.close()
        return {"ok": False, "msg": "订单不存在"}
    order = dict(order)
    if order["status"] == "paid":
        conn.close()
        return {"ok": False, "msg": "订单已支付"}
    plan = get_plan(order["plan_id"])
    now = datetime.now()
    conn.execute("UPDATE orders SET status='paid', paid_at=datetime('now','localtime') WHERE order_no=?",
                 (order_no,))

    sub = conn.execute("SELECT * FROM subscriptions WHERE user_id=?", (order["user_id"],)).fetchone()
    if sub:
        sub = dict(sub)
        # 已有订阅：从现有到期时间续期；已过期的从今天起算
        base = datetime.strptime(sub["expires_at"], "%Y-%m-%d %H:%M:%S") if sub["expires_at"] else now
        if base < now:
            base = now
    else:
        base = now
    expires = base + timedelta(days=int(plan["duration_days"] or 0))

    conn.execute(
        "INSERT INTO subscriptions (user_id, plan_id, status, started_at, expires_at) "
        "VALUES (?,?,?,?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET plan_id=excluded.plan_id, status='active', "
        "started_at=excluded.started_at, expires_at=excluded.expires_at",
        (order["user_id"], order["plan_id"], "active",
         now.strftime("%Y-%m-%d %H:%M:%S"), expires.strftime("%Y-%m-%d %H:%M:%S")),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "msg": "支付成功", "plan_name": plan["name"],
            "expires_at": expires.strftime("%Y-%m-%d %H:%M:%S")}


def get_subscription(user_id):
    """查询某用户的当前订阅状态（含套餐信息）。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT s.*, p.name AS plan_name, p.agent_limit, p.price AS plan_price "
        "FROM subscriptions s JOIN plans p ON p.id = s.plan_id WHERE s.user_id=?",
        (user_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_orders(user_id=None):
    """订单列表（可指定用户）。"""
    conn = get_conn()
    if user_id:
        rows = conn.execute(
            "SELECT o.*, p.name AS plan_name FROM orders o JOIN plans p ON p.id=o.plan_id "
            "WHERE o.user_id=? ORDER BY o.id DESC",
            (user_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT o.*, p.name AS plan_name FROM orders o JOIN plans p ON p.id=o.plan_id "
            "ORDER BY o.id DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
