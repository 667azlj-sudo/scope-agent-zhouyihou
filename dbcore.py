# -*- coding: utf-8 -*-
"""
dbcore.py —— 数据库抽象层

生产环境走 PostgreSQL（设置 DATABASE_URL），开发/测试回退 SQLite（DB_PATH）。
上层模块统一通过 get_conn() 拿连接，SQL 沿用 SQLite 的 `?` 占位符，并可用两个 token：
  __PK__   → SERIAL PRIMARY KEY (PG) / INTEGER PRIMARY KEY AUTOINCREMENT (SQLite)
  __NOW__  → 本地时间字符串表达式（YYYY-MM-DD HH:MM:SS）
"""
import sqlite3

from config import DATABASE_URL, DB_PATH


def is_pg():
    return bool(DATABASE_URL)


def _now_expr():
    if is_pg():
        return "to_char(CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Shanghai', 'YYYY-MM-DD HH24:MI:SS')"
    return "datetime('now','localtime')"


def _sub(sql):
    """把上层统一写法翻译成目标方言。"""
    if is_pg():
        sql = sql.replace("?", "%s")
        sql = sql.replace("__PK__", "SERIAL PRIMARY KEY")
    else:
        sql = sql.replace("__PK__", "INTEGER PRIMARY KEY AUTOINCREMENT")
    return sql.replace("__NOW__", _now_expr())


def get_conn():
    """返回统一连接：PG 为 psycopg3 连接（dict 行），SQLite 为 dict 行工厂连接。"""
    if is_pg():
        import psycopg
        from psycopg.rows import dict_row
        return _Conn(psycopg.connect(DATABASE_URL, row_factory=dict_row))
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = lambda cursor, row: {
        col[0]: row[idx] for idx, col in enumerate(cursor.description or [])
    }
    return _Conn(conn)


class _Conn:
    """统一连接包装：execute / executescript 前做方言替换，其余委托。"""

    def __init__(self, raw):
        self._raw = raw

    def execute(self, sql, params=()):
        s = _sub(sql)
        if params:
            return self._raw.execute(s, params)
        return self._raw.execute(s)

    def executescript(self, sql):
        if is_pg():
            for stmt in sql.split(";"):
                stmt = stmt.strip()
                if stmt:
                    self._raw.execute(_sub(stmt))
        else:
            self._raw.executescript(_sub(sql))

    def commit(self):
        return self._raw.commit()

    def close(self):
        return self._raw.close()

    def rollback(self):
        return self._raw.rollback()


def insert_id(conn, sql, params=()):
    """执行 INSERT 并返回新行自增 id（PG 用 RETURNING id，SQLite 用 lastrowid）。"""
    if is_pg():
        s = sql.rstrip().rstrip(";")
        if "RETURNING" not in s.upper():
            s += " RETURNING id"
        cur = conn.execute(s, params)
        row = cur.fetchone()
        return row["id"] if row else None
    cur = conn.execute(sql, params)
    return cur.lastrowid


def ensure_column(conn, table, column, definition):
    """幂等地确保列存在。table/column/definition 均为内部常量，非用户输入。"""
    if is_pg():
        conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {definition}")
    else:
        cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


# 完整性错误（唯一约束等），覆盖 PG 与 SQLite
try:
    import psycopg
    IntegrityErrors = (sqlite3.IntegrityError, psycopg.errors.IntegrityError)
except Exception:  # noqa: BLE001
    IntegrityErrors = (sqlite3.IntegrityError,)
