# -*- coding: utf-8 -*-
"""test_pg_dialect.py —— PostgreSQL 方言生成自测（无需真实 PG，只验证 SQL 翻译）

运行：py test_pg_dialect.py
"""
import os

os.environ["DATABASE_URL"] = "postgresql://u:p@localhost:5432/db"

import dbcore


def main():
    fails = []

    def check(name, cond):
        print(("PASS" if cond else "FAIL") + "  " + name)
        if not cond:
            fails.append(name)

    check("PG 模式识别", dbcore.is_pg())

    s = dbcore._sub("SELECT * FROM t WHERE a=? AND id __PK__ AND ts=__NOW__")
    check("? → %s", "%s" in s and "?" not in s)
    check("__PK__ → SERIAL PRIMARY KEY", "SERIAL PRIMARY KEY" in s and "__PK__" not in s)
    check("__NOW__ → to_char", "to_char(" in s and "__NOW__" not in s)

    ddl = dbcore._sub("CREATE TABLE t (id __PK__, created_at TEXT DEFAULT (__NOW__));")
    check("DDL SERIAL", "SERIAL PRIMARY KEY" in ddl)
    check("DDL 时间函数", "to_char(CURRENT_TIMESTAMP" in ddl)

    print("\n" + ("ALL PASS" if not fails else "FAILED: " + str(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
