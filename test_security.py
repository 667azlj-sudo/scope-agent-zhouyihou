# -*- coding: utf-8 -*-
"""test_security.py —— 安全加固自测（密码盐化 / token 过期 / 登出 / 验证码防刷）

运行：py test_security.py
"""
import os
import tempfile

# 用临时目录做 SQLite 测试，避免污染真实数据
os.environ["DATA_DIR"] = tempfile.mkdtemp()

import hashlib
import time

import auth


def main():
    fails = []

    def check(name, cond):
        print(("PASS" if cond else "FAIL") + "  " + name)
        if not cond:
            fails.append(name)

    auth.init_users()

    # 1. 随机盐：同一密码两次哈希应不同
    h1 = auth.hash_password("p@ssw0rd")
    h2 = auth.hash_password("p@ssw0rd")
    check("随机盐（同密码哈希不同）", h1 != h2)

    # 2. 往返校验 + 错误密码拒绝
    check("正确密码校验通过", auth.verify_password("p@ssw0rd", h1))
    check("错误密码校验拒绝", not auth.verify_password("wrong", h1))

    # 3. 旧固定盐格式兼容
    legacy = hashlib.pbkdf2_hmac("sha256", b"legacy", b"scope_agent_salt", 100000).hex()
    check("旧格式密码兼容", auth.verify_password("legacy", legacy))

    # 4. 注册 → 登录 → token 校验 → 登出
    ok, _ = auth.register("boss", "pw123", "manager")
    check("注册成功", ok)
    token, user = auth.login("boss", "pw123")
    check("登录拿到 token", bool(token) and bool(user))
    check("token 反查用户", auth.get_user_by_token(token) is not None)
    auth.logout(token)
    check("登出后 token 失效", auth.get_user_by_token(token) is None)

    # 5. token 过期
    token2, _ = auth.login("boss", "pw123")
    conn = auth.get_conn()
    conn.execute("UPDATE sessions SET expires_at=? WHERE token=?", (int(time.time()) - 10, token2))
    conn.commit()
    conn.close()
    check("过期 token 失效", auth.get_user_by_token(token2) is None)

    # 6. 验证码防刷
    auth.create_verify_code("13800138000")
    can, _ = auth.can_send_code("13800138000")
    check("60秒内禁止重复发验证码", not can)

    # 7. query_db 只读限制
    import agent_framework as af
    af.init_agent_db()
    check("query_db 拒绝非SELECT", "error" in af.query_db(1, "DROP TABLE x"))
    check("query_db 拒绝敏感表", "error" in af.query_db(1, "SELECT * FROM users"))
    check("query_db 拒绝敏感字段", "error" in af.query_db(1, "SELECT password_hash FROM agents"))
    check("query_db 拒绝多语句", "error" in af.query_db(1, "SELECT * FROM agents; DROP TABLE x"))
    r = af.query_db(1, "SELECT * FROM agent_tasks")
    check("query_db 允许合法查询", "error" not in r and r.get("columns") is not None)

    # 8. Bearer 解析
    check("parse_bearer 正常", auth.parse_bearer("Bearer abc123") == "abc123")
    check("parse_bearer 空/异常", auth.parse_bearer("") == "" and auth.parse_bearer("Basic xyz") == "")

    print("\n" + ("ALL PASS" if not fails else "FAILED: " + str(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
