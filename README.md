# Scope Agent

企业团队用的**权责分工与多智能体协作**平台。接上大模型以后，系统能拆解项目、自动给子任务定保密等级、派发给成员的专属 Agent，并按任务难度给成果计价。自带一套微信风格的团队通信界面。

## 能做什么

- **项目拆解**：给一段目标描述，拆成一串可执行的子任务，同时标注每项的保密等级（机密 / 一般）。
- **分级派发**：机密任务留在内部处理，一般任务可以交给外包，最终由负责人拍板。
- **多智能体协作**：每位成员一个专属 Agent，职责内的任务自动派给它；Agent 之间能发消息、能提交成果。
- **成果审核与计价**：员工提交成果，负责人审核；通过后按「基础工资 × 难度系数」计价，也可以对个别成员豁免绩效。
- **团队通信**：微信风格的群聊 / 私聊，支持 2 分钟内撤回、位置卡片、图片消息。
- **多模知识检索**：向量 + BM25 混合检索，可选 GraphRAG；配合长期记忆，Agent 越用越懂你。
- **双模型引擎**：本地 Ollama 或云端 DeepSeek，随时切换。

## 三种角色

| 角色 | 看到的界面 |
|---|---|
| 负责人 | 工作台（待办与团队概览）、拆任务分级、审核成果、给成员定基础工资 |
| 员工 | 我的任务（接活、提交成果、看绩效）、我的 Agent、团队消息 |
| 普通成员 | 项目、消息、好友 |

## 技术栈

| 层 | 技术 |
|---|---|
| 大模型 | Ollama（gemma4）/ DeepSeek |
| 向量化 | bge-m3 |
| 后端 | FastAPI + Uvicorn |
| 数据库 | SQLite |
| 前端 | Vue 3 + Vite + Element Plus |
| 检索 | 向量 + BM25 混合 / GraphRAG |

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动 Ollama（本地模型路径按自己机器设置）
$env:OLLAMA_MODELS='D:\'
ollama serve

# 3. 启动后端
uvicorn app:app --reload --host 127.0.0.1 --port 8000

# 4. 启动前端（另开一个终端）
cd frontend
npm install
npm run dev
```

- 后端接口文档：<http://127.0.0.1:8000/docs>
- 前端页面：<http://127.0.0.1:5173>

> 默认用本地 Ollama。想切到云端 DeepSeek，调用 `POST /api/config/llm` 填入 API Key 即可。

## 目录结构

```
scope-agent/
├── app.py               FastAPI 后端与路由
├── agent.py             ReAct 智能体（读文档 / 生成任务树 / 发消息）
├── agent_framework.py   多 Agent 框架核心（任务 / 提交 / 工资）
├── llm.py               双引擎 LLM 封装
├── knowledge.py         知识库（向量 + BM25）
├── graphrag.py          GraphRAG 图检索
├── splitter.py          AI 项目拆解
├── router.py            任务分级路由
├── db.py                业务数据（项目 / 任务 / 用户）
├── auth.py              注册登录与角色
├── chat.py              会话 / 消息 / 文件 / 撤回 / 位置 / 图片
└── frontend/            Vue 3 前端（微信风格移动端界面）
```
