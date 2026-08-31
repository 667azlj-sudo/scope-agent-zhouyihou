# -*- coding: utf-8 -*-
"""
router.py —— 任务分级路由
简单任务算法自动分配；模糊任务提交负责人确认（附 AI 建议）
"""
import json


def clean_json(text):
    """清理 LLM 输出的 markdown 标记"""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.rsplit("```", 1)[0]
    return text.strip()


def route(tasks_json):
    """把事项清单按"简单/模糊"分流，返回 (simple, fuzzy) 两份清单"""
    items = json.loads(clean_json(tasks_json))

    simple = []   # 简单事项 → 算法自动处理
    fuzzy = []    # 模糊事项 → 待负责人确认

    for it in items:
        if it.get("type") == "简单":
            it["status"] = "auto_assigned"     # 算法自动分配
            simple.append(it)
        else:
            it["status"] = "pending_review"    # 待负责人确认
            fuzzy.append(it)

    return simple, fuzzy


if __name__ == "__main__":
    from splitter import split_project

    desc = "开发一个电商小程序，包含商品展示、购物车、支付、订单管理、客服系统"
    tasks_json = split_project(desc)

    simple, fuzzy = route(tasks_json)

    print("===== 分级路由结果 =====")
    print(f"\n【简单事项 {len(simple)} 个】→ 算法自动分配，无需人工：")
    for it in simple:
        print(f"  ✅ {it['task']}")

    print(f"\n【模糊事项 {len(fuzzy)} 个】→ 待负责人确认：")
    for it in fuzzy:
        print(f"  ⚠️  {it['task']}")
        if it.get("suggestion"):
            print(f"     💡 AI建议：{it['suggestion']}")
