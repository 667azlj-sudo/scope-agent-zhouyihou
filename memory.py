# -*- coding: utf-8 -*-
"""
memory.py —— 用户画像记忆
update_memory：用 LLM 提炼对话 → 更新用户画像（存 users.memory）
get_memory：读取用户画像
"""
import sqlite3

import llm

DB_PATH = "scope_agent.db"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_memory(user_id):
    """读取某用户的画像（JSON 字符串）"""
    conn = get_conn()
    row = conn.execute("SELECT memory FROM users WHERE id=?", (user_id,)).fetchone()
    conn.close()
    return row["memory"] if row and row["memory"] else "{}"


def update_memory(user_id, dialogue):
    """用 LLM 提炼对话，更新用户画像，返回更新后的画像"""
    old = get_memory(user_id)
    prompt = f"""你是用户画像整理助手。根据新对话更新用户画像。
【现有画像】：{old}
【新对话】：{dialogue}
提炼用户稳定信息（身份、偏好、习惯），合并进画像。
只输出 JSON 对象，格式 {{"preferences": [...], "facts": [...]}}，不要其他文字。"""
    msg = llm.chat([{"role": "user", "content": prompt}])
    new_memory = msg.content
    conn = get_conn()
    conn.execute("UPDATE users SET memory=? WHERE id=?", (new_memory, user_id))
    conn.commit()
    conn.close()
    return new_memory
