# Scope Agent

企业级**项目权责分化与智能协作系统**。基于大语言模型自动解析项目资料，生成任务分解树与权责分配，支持团队协作与多模知识检索。

## 核心能力

- **AI 项目解析**：读取项目文档，自动生成结构化任务分解树，并标注每个任务的负责人
- **智能路由**：简单任务由算法自动分配，模糊任务提交负责人确认（附带 AI 建议）
- **权责审批流**：负责人拥有唯一确认/审批权，员工协商后的变更需负责人批准（状态机驱动）
- **多模检索**：向量 + BM25 混合检索，支持 GraphRAG 图增强检索（可配置）
- **Agent 智能体**：基于 ReAct 的多轮智能体，具备读文档、生成任务树、发送消息能力
- **团队通信**：群聊与私聊
- **双引擎**：本地 Ollama / 云端 LLM 双模式，通过配置切换

## 技术栈

| 层 | 技术 |
|---|---|
| LLM | Ollama（gemma4）/ DeepSeek |
| 向量化 | bge-m3 |
| 后端 | FastAPI + Uvicorn |
| 数据库 | SQLite |
| 检索 | 向量 + BM25 混合 / GraphRAG 图检索 |

## 快速开始

```bash
pip install -r requirements.txt

# 初始化数据库并演示 AI 拆解流程
python db.py

# 权限审批流演示
python auth.py

# 启动 Web 服务
python app.py

# 访问交互式 API 文档
# http://127.0.0.1:8000/docs
```

## 主要 API

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/projects` | 创建项目（解析+拆解+入库） |
| GET | `/api/projects/{id}/tasks` | 查询项目事项 |
| POST | `/api/tasks/{id}/confirm` | 负责人确认 |
| POST | `/api/tasks/{id}/propose` | 员工协商 |
| POST | `/api/tasks/{id}/approve` | 负责人审批 |
| POST | `/api/chats` | 创建会话 |
| POST | `/api/chats/{id}/messages` | 发送消息 |
| POST | `/api/agent/chat` | Agent 对话（含知识检索/任务树） |
| POST | `/api/knowledge/build` | 构建知识库 |
| POST | `/api/config/llm` | 配置云端 LLM |
| POST | `/api/config/graphrag` | 配置 GraphRAG 开关 |

## 项目结构

```
scope-agent/
├── app.py        Web 后端（FastAPI）
├── agent.py      ReAct 智能体
├── llm.py        双引擎 LLM 封装
├── knowledge.py  知识库（向量+BM25 混合检索）
├── graphrag.py   GraphRAG 图检索
├── splitter.py   AI 项目解析
├── router.py     任务分级路由
├── db.py         数据持久化
├── auth.py       权限审批流
└── chat.py       聊天 & 文件
```
