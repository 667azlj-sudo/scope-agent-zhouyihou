# Scope Agent

企业团队的权责分工与多智能体协作系统。接上大模型后，能拆解任务、按保密等级分级派发、给成员的专属 Agent 派活，并按难度计价。带一套微信风格的团队聊天。

## 功能

- **任务拆解**：一段描述拆成可执行子任务，标出机密 / 一般。
- **分级派发**：机密任务留内部，一般任务可外包，由负责人拍板。
- **两级审核 + 报价**：内部任务由经理 Agent 发给员工 Agent，员工 Agent 结合本地记录报「工时 + 工资」，经理通过后才正式派发；员工做完提交，再由经理审核结算。
- **任务大厅**：查知识库发现没人能接手的任务，经理选候选人发布，只有候选人可见并可接取。
- **外包大厅**：外包任务发布到大厅，其他公司的人也能接。
- **能力知识库**：员工可上传文档、导入聊天记录、或让 Agent 读取本地文件夹，RAG 成个人能力库；Agent 据此判断任务适配度，并据此给 Agent 重新命名。
- **自动建 Agent**：注册即建专属 Agent（不替人干活，只做审核、报价、协作）。
- **公司邀请码**：负责人注册建公司拿邀请码，员工凭码加入，自动进总公司群。
- **工资结算打款**：审核通过生成结算记录，负责人一键打款，员工看到账明细。
- **套餐订阅**：购买套餐解锁 Agent 数量与有效期（订单/订阅/支付已跑通，支付网关留接口，当前为模拟支付）。
- **手机号注册**：阿里云短信验证码，登录支持手机号或用户名。
- **团队聊天**：群聊 / 私聊，支持撤回（2 分钟内）、位置、图片、@ 成员、未读置顶。
- **模型**：本地 Ollama 或云端 DeepSeek，可切换。

## 角色

| 角色 | 界面 |
|---|---|
| 负责人 | 工作台、拆任务分级、审核报价与成果、结算打款、定工资、任务条件库 |
| 员工 | 我的任务、外包大厅、消息、我的（工资 / 到账 / 工作记录） |
| 普通成员 | 外包大厅、任务、消息、好友、我的 |

## 技术栈

| 层 | 技术 |
|---|---|
| 大模型 | Ollama（gemma4）/ DeepSeek |
| 向量化 | bge-m3（不可用时退化为 BM25） |
| 后端 | FastAPI + Uvicorn |
| 数据库 | PostgreSQL（生产，DATABASE_URL）/ SQLite（开发回退） |
| 前端 | Vue 3 + Vite + Element Plus |

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 启动 Ollama（PowerShell，模型路径按自己机器设置）
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

> 默认用本地 Ollama；想切到云端 DeepSeek，设环境变量 `DEEPSEEK_API_KEY` 或调用 `POST /api/config/llm`。

> 手机号验证码：配置 `ALIYUN_AK_ID`、`ALIYUN_AK_SECRET`、`ALIYUN_SIGN_NAME`、`ALIYUN_TEMPLATE_CODE` 后走真实阿里云短信；未配置时自动退回本地模拟（验证码在后端日志/接口返回）。

## 个人知识库 + DeepSeek RAG

员工在本地建立个人知识库（信息 / 习惯 / 文档 / 聊天记录），RAG 时由 **DeepSeek 读取用户信息与习惯**并个性化作答。

- 检索用**本地 BM25**（jieba），不依赖 Ollama / bge-m3；个人知识库较小时整库交给 DeepSeek 阅读，较大时用 BM25 收窄。
- 生成走 **DeepSeek API**（`llm.chat`，配置 `DEEPSEEK_API_KEY` 即启用，否则回退本地模型）。

接口：
| 方法 | 路径 | 说明 |
|---|---|---|
| GET / POST | `/api/profile/{uid}` | 读取 / 保存用户「信息与习惯」画像 |
| POST | `/api/profile/{uid}/index` | 把画像 + 工作记录 + 聊天记录 + 能力库索引进本地知识库 |
| POST | `/api/agent/chat` | `{user_id, message}` → DeepSeek 读取画像与片段作答 |

## 生产部署（Docker Compose）

```bash
cp .env.example .env   # 填入 DEEPSEEK_API_KEY、阿里云短信密钥等
docker compose up -d --build
```

- 前端由 Nginx 托管，并反向代理 `/api`、`/uploads` 到后端，入口默认 `http://<主机>:80`。
- 数据（SQLite、上传文件、知识库）持久化在 `app_data` 卷（容器内 `/app/data`，由环境变量 `DATA_DIR` 控制）。
- 全部环境变量见 `.env.example`。

> 注意：生产走 PostgreSQL（`DATABASE_URL`），开发回退 SQLite；支付网关仍为模拟，需接入微信/支付宝并替换 `payment.pay_order()`。

## 目录结构

```
scope-agent/
├── app.py               FastAPI 后端与路由
├── agent_framework.py   多 Agent 框架（任务 / 报价 / 提交 / 结算）
├── ability_kb.py        个人能力知识库（RAG，按用户分文件）
├── llm.py               LLM 封装（本地 / 云端）
├── knowledge.py         团队知识库（向量 + BM25）
├── graphrag.py          GraphRAG 图检索
├── splitter.py          任务拆解
├── router.py            任务分级路由
├── config.py            数据目录与环境变量（DATA_DIR 等）
├── db.py                业务数据（项目 / 任务 / 用户）
├── auth.py              注册登录与角色（手机号 + 验证码）
├── sms.py               短信发送（阿里云，未配密钥时模拟）
├── company.py           公司 + 邀请码
├── payment.py           套餐 / 订单 / 订阅（支付网关留接口）
├── chat.py              会话 / 消息 / 撤回 / 位置 / 图片 / 群成员 / 加群申请
├── memory.py            用户画像记忆
└── frontend/            Vue 3 前端（移动端）
```
