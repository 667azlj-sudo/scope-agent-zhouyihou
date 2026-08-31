# -*- coding: utf-8 -*-
"""
agent.py —— ReAct 智能体
通过工具调用（读文档、生成任务树、发送消息）完成多轮推理
兼容本地与云端 LLM 的工具调用格式
"""
import json
import os

import auth
import graphrag
import knowledge
import llm

UPLOADS_DIR = "uploads"


# ---- 工具定义（JSON Schema，告诉模型有哪些工具）----
AGENT_TOOLS = [
    {"type": "function", "function": {
        "name": "read_documents",
        "description": "读取客户上传的资料文件，返回文本内容",
        "parameters": {"type": "object", "properties": {
            "filename": {"type": "string", "description": "文件名，如 '需求.txt'"}},
            "required": ["filename"]}}},
    {"type": "function", "function": {
        "name": "create_task_tree",
        "description": "根据项目资料生成项目完成树（树状结构，叶子是具体任务并标注负责员工）",
        "parameters": {"type": "object", "properties": {
            "project_name": {"type": "string", "description": "项目名称"}},
            "required": ["project_name"]}}},
    {"type": "function", "function": {
        "name": "send_message",
        "description": "发送消息到群聊或员工私聊",
        "parameters": {"type": "object", "properties": {
            "chat_id": {"type": "integer", "description": "会话 id"},
            "content": {"type": "string", "description": "消息内容"}},
            "required": ["chat_id", "content"]}}},
    {"type": "function", "function": {
        "name": "search_knowledge",
        "description": "在项目知识库里检索相关信息",
        "parameters": {"type": "object", "properties": {
            "question": {"type": "string", "description": "要查询的问题"}},
            "required": ["question"]}}},
]


# ---- 工具实现 ----
def _read_documents(filename):
    path = os.path.join(UPLOADS_DIR, filename)
    if not os.path.exists(path):
        return f"文件不存在：{filename}（请先上传到 uploads/）"
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"读取失败：{e}"


def _create_task_tree(project_name):
    """生成项目完成树：LLM 根据项目信息 + 员工名单，生成树状 JSON"""
    # 1. 取员工名单
    employees = [u["name"] for u in auth.get_all_users()]
    if not employees:
        employees = ["未分配"]

    # 2. 检索知识库里的项目信息作为依据
    info = knowledge.search(project_name, top_k=5)
    context = "\n".join(t for t, s in info) or "（无知识库信息，请基于项目名称合理规划）"

    # 3. LLM 生成树状 JSON
    prompt = f"""根据项目信息生成「项目完成树」（JSON 树状结构）。

项目信息：
{context}

可选员工（分配给他们）：{", ".join(employees)}

要求：
1. 树状结构：项目根节点 → 阶段 → 具体任务（叶子）
2. 每个任务标注负责员工（从可选员工里选）
3. 叶子任务尽量具体、可执行
4. 只输出 JSON，格式：
{{"name": "项目名", "children": [{{"name": "阶段1", "children": [{{"name": "任务1", "assignee": "员工名"}}]}}]}}

只输出 JSON，不要其他任何文字。"""
    msg = llm.chat([{"role": "user", "content": prompt}])
    return msg.content


def _send_message(chat_id, content):
    """发消息到群聊/私聊（Agent 代发，用第一个用户作为发送者）"""
    import chat
    users = auth.get_all_users()
    sender_id = users[0]["id"] if users else 1
    chat.send_message(chat_id, sender_id, content)
    return f"已发送到会话 {chat_id}"


def _search_knowledge(question):
    """Agentic RAG：查项目知识库（混合检索）；若启用了 GraphRAG，补充图多跳路径"""
    results = knowledge.search(question, top_k=3)
    parts = [f"[相关度 {s:.2f}] {t}" for t, s in results]
    if graphrag.is_enabled() and graphrag._graph:
        paths = graphrag.search(question)
        if paths:
            parts.append("[图检索] " + " | ".join(
                " -> ".join(f"{e}({r})" for e, r, _ in p) for p in paths))
    if not parts:
        return "知识库为空，没有找到相关信息"
    return "\n\n".join(parts)


TOOL_FUNCS = {
    "read_documents": _read_documents,
    "create_task_tree": _create_task_tree,
    "send_message": _send_message,
    "search_knowledge": _search_knowledge,
}


def run_agent(user_input, system_prompt, max_rounds=10):
    """ReAct 循环：模型请求工具 → 执行 → 回填结果 → 重复，直至模型不再请求"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input},
    ]

    for r in range(1, max_rounds + 1):
        msg = llm.chat(messages, tools=AGENT_TOOLS)

        # 模型没请求工具 → 给出最终答案，结束
        if not msg.tool_calls:
            return msg.content or "", r

        # 记住模型这轮的请求（tool_calls 格式按模型类型区分）
        if llm.is_cloud():
            # DeepSeek/OpenAI 格式：要带 id 和 type
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in msg.tool_calls],
            })
        else:
            # Ollama 格式
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {"function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in msg.tool_calls],
            })

        # 执行工具
        for tc in msg.tool_calls:
            name = tc.function.name
            args = tc.function.arguments
            if isinstance(args, str):      # DeepSeek 是 JSON 字符串
                args = json.loads(args)
            result = TOOL_FUNCS[name](**args)
            print(f"[agent] 调用 {name}({args}) → {str(result)[:60]}")

            # 回填工具结果（按模型类型区分）
            if llm.is_cloud():
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": str(result)})
            else:
                messages.append({"role": "tool", "name": name, "content": str(result)})

    return "达到最大轮数", max_rounds


if __name__ == "__main__":
    import sqlite3
    # 确保用户存在（生成树要标员工）
    auth.init_users()
    conn = sqlite3.connect("scope_agent.db")
    for name, role in [("张总", "manager"), ("李四", "employee"), ("王五", "employee"), ("张三", "employee")]:
        conn.execute("INSERT OR IGNORE INTO users (name, role) VALUES (?,?)", (name, role))
    conn.commit()
    conn.close()

    # 构建项目知识库
    knowledge.build_knowledge([
        "公司今年预算 10 万，工期一个月，做一个企业官网。",
        "官网包含首页、产品展示、新闻、联系我们模块。",
        "客户是制造业公司，希望突出品牌形象。",
    ])
    print("知识库已建立，员工已就绪")

    # 测试：agent 自主生成项目完成树
    sys_prompt = "你是项目规划助手。用户要求生成项目完成树时用 create_task_tree；需要查项目信息时用 search_knowledge。"
    ans, rounds = run_agent("请为这个「企业官网」项目生成项目完成树，每个任务标注好负责员工", sys_prompt)
    print(f"\n[共 {rounds} 轮] Agent 回答：\n{ans}")
