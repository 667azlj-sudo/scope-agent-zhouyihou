# Scope Agent 多 Agent 协作框架设计

## 一、架构总览

```
┌─────────────────────────────────────────────┐
│ Agent 层                                      │
│   员工 Agent（每员工一个，登录即绑定：<name>_agent）│
│   职能 Agent（项目经理 / 开发 / 测试，可选）        │
│   经理 Agent（中心调度，最高优先级）               │
├─────────────────────────────────────────────┤
│ 交流结构（经理 > 平级）                          │
│   经理线程：经理agent 拆任务 → 派员工 → 收结果 → 审核│
│   平级线程：员工agent <—消息—> 其他agent（互求）   │
│   优先级：经理指令优先于平级请求                    │
├─────────────────────────────────────────────┤
│ Agent 工具化（function calling 模式）            │
│   query_db(问题)      → 查数据库/知识库          │
│   message_agent(对方) → 给其他agent发消息        │
│   get_task()          → 领分配给我的任务         │
│   submit_work(成果)   → 提交工作                │
│   review(提交)        → 审核                   │
├─────────────────────────────────────────────┤
│ 任务流：任务 → 经理拆成子任务(具体要求) → 派员工      │
│         → 员工agent干活 → 提交 → 审核(通过/打回)    │
├─────────────────────────────────────────────┤
│ 绩效层                                          │
│   审核成果 → 按难度标价 → 更新工资                │
└─────────────────────────────────────────────┘
```

## 二、交流结构

- **经理线程**：经理 agent 是中心，负责拆任务、派发、审核、汇总
- **平级线程**：员工 agent 之间通过消息互相请求信息、接力
- **优先级**：经理指令 > 平级请求（冲突时先执行经理）

## 三、Agent 工具（function calling 模式）

agent 的能力是一组可调用工具：
- `query_db`: 向数据库/知识库寻求信息
- `message_agent`: 向指定 agent 发消息
- `get_task`: 获取自己的任务
- `submit_work`: 提交成果
- `review`: 审核提交

## 四、任务流

1. 用户提交任务 → 经理 agent 拆解成子任务（每项含具体要求）
2. 经理派发给对应员工 agent
3. 员工 agent 干活（可 query_db / message_agent）
4. 提交工作 → 经理审核（通过 / 打回修改）

## 五、定价与工资逻辑

- **绩效标价** = 员工原工资 × 难度系数（0.5 ~ 3 倍）
- **难度系数** = 算法(任务复杂度 / 风险 / 紧急度)
- **员工工资** = 基础工资 + 绩效标价
- **经理豁免**：经理可配置白名单，豁免员工不适用绩效规则（工资 = 基础工资）

## 六、可配置模板（用户可改，但警告）

- 角色定义模板（agent 的 system prompt / 职责）
- 交流规则模板（谁找谁、优先级）
- 修改时会提示"警告：不建议修改，可能破坏协作"

## 七、数据表（建议）

- `agents`: id, user_id, role_type(employee/functional/manager), name, config(json)
- `tasks`: id, project_id, title, detail, difficulty, status, assignee_agent
- `submissions`: id, task_id, agent_id, content, status, price
- `agent_messages`: id, from_agent, to_agent, content, priority
- `salaries`: user_id, base_salary, exempt(是否豁免绩效)
