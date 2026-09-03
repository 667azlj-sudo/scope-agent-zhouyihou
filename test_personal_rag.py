# -*- coding: utf-8 -*-
"""test_personal_rag.py —— 个人本地知识库 + DeepSeek RAG 自测

运行：py test_personal_rag.py
"""
import os
import sys
import tempfile
import types

import personal_rag


def main():
    fails = []

    def check(name, cond):
        print(("PASS" if cond else "FAIL") + "  " + name)
        if not cond:
            fails.append(name)

    # 用临时目录，避免污染真实数据
    personal_rag._KB_DIR = os.path.join(tempfile.mkdtemp(), "kb")

    # 1. 画像（信息与习惯）写入/读取
    r = personal_rag.upsert_profile(1, "我是后端开发，3 年经验", "习惯上午深度工作，喜欢简洁文档")
    check("画像写入", r["ok"])
    p = personal_rag.get_profile(1)
    check("画像读取", p["info"].startswith("我是后端") and "上午" in p["habits"])

    # 2. 片段 + BM25 检索
    personal_rag.add_chunks(1, [
        "负责公司官网后端接口开发",
        "喜欢用 Python 和 Go",
        "近期在学 Kubernetes",
    ], "manual")
    hits = personal_rag.search(1, "后端 用什么语言", top_k=3)
    check("检索命中", len(hits) > 0 and any("Python" in h["text"] for h in hits))

    # 3. ask()：stub llm.chat，验证 DeepSeek 收到了画像 + 检索片段
    fake_llm = types.ModuleType("llm")
    captured = {}

    class FakeMsg:
        def __init__(self, c):
            self.content = c

    def fake_chat(messages, tools=None):
        captured["messages"] = messages
        return FakeMsg("这是个性化回答")

    fake_llm.chat = fake_chat
    sys.modules["llm"] = fake_llm

    res = personal_rag.ask(1, "我该学什么语言")
    check("ask 返回回答", res["ok"] and res["answer"] == "这是个性化回答")
    check("ask 使用了画像", res["profile_used"] is True)

    joined = " ".join(m["content"] for m in captured["messages"])
    check("prompt 含用户信息", "后端开发" in joined)
    check("prompt 含用户习惯", "深度工作" in joined)
    check("prompt 含检索片段", "Python" in joined)

    print("\n" + ("ALL PASS" if not fails else "FAILED: " + str(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
