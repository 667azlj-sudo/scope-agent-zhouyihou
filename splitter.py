# -*- coding: utf-8 -*-
"""
splitter.py —— AI 拆解引擎

统一走 llm.chat()（云端 DeepSeek 优先，未配置 key 时回退本地）。
"""
import sys

import llm


def set_cloud_key(api_key):
    """切换到云端 DeepSeek（转发给 llm 模块）。"""
    return llm.set_cloud_key(api_key)


def is_cloud():
    """当前是否用云端 DeepSeek"""
    return llm.is_cloud()


def split_project(project_desc):
    """把项目描述拆解成结构化事项清单，返回 JSON 字符串"""
    prompt = f"""
你是项目落地规划助手。根据下面的项目描述，拆解出「项目落地事项」清单。

【项目描述】：
{project_desc}

要求：
1. 拆解出所有需要落地的事项（具体、可执行、不遗漏）
2. 给每个事项判断类型：
   - "简单"：明确、无争议、有固定做法（如"每天同步进度"）
   - "模糊"：有歧义、需要负责人决策（如"谁来负责测试"）
3. 对"模糊"事项，给出你的 AI 建议（建议怎么处理、分配给谁）

输出 JSON 数组，每条格式：
{{"task": "事项内容", "type": "简单"或"模糊", "suggestion": "AI建议（简单事项可留空）"}}

只输出 JSON 数组，不要其他任何文字。
"""
    resp = llm.chat([{"role": "user", "content": prompt}])
    return resp.content


if __name__ == "__main__":
    if len(sys.argv) > 1:
        desc = " ".join(sys.argv[1:])
    else:
        desc = "开发一个电商小程序，包含商品展示、购物车、支付、订单管理、客服系统"

    mode = "DeepSeek 云端" if is_cloud() else "本地 gemma4"
    print(f"===== 当前模型：{mode} =====")
    print(split_project(desc))
