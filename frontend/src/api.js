// src/api.js —— 后端 API 封装
const BASE = "http://127.0.0.1:8000"

async function api(path, method = "GET", body = null, token = null) {
  const headers = { "Content-Type": "application/json" }
  if (token) headers["Authorization"] = "Bearer " + token
  const res = await fetch(BASE + path, {
    method,
    headers,
    body: body ? JSON.stringify(body) : null,
  })
  return res.json()
}

export const register = (name, password, role, phone, code, companyName, inviteCode, position) => api("/api/register", "POST", { name, password, role, phone, code, company_name: companyName, invite_code: inviteCode, position })
export const login = (account, password) => api("/api/login", "POST", { account, password })
export const smsSend = (phone) => api("/api/sms/send", "POST", { phone })
export const agentChat = (message, userId) => api("/api/agent/chat", "POST", { message, user_id: userId })
export const createProject = (description) => api("/api/projects", "POST", { description })
export const getTasks = (pid) => api(`/api/projects/${pid}/tasks`)
export const buildKnowledge = (texts) => api("/api/knowledge/build", "POST", { texts })
export const addFriend = (userId, targetId, role) => api("/api/friends/add", "POST", { user_id: userId, target_id: targetId, requester_role: role })
export const getFriends = (userId) => api(`/api/friends/${userId}`)
export const getPendingFriends = () => api("/api/friends/pending")
export const approveFriend = (fid, approve, role) => api(`/api/friends/${fid}/approve`, "POST", { approve, approver_role: role })
export const createChat = (type, name, memberIds) => api("/api/chats", "POST", { type, name, member_ids: memberIds })
export const sendMessage = (cid, token, content) => api(`/api/chats/${cid}/messages`, "POST", { token, content })
export const getMessages = (cid) => api(`/api/chats/${cid}/messages`)
export const withdrawMessage = (mid, token) => api(`/api/messages/${mid}/withdraw`, "POST", { token })
export function sendImage(cid, token, file) {
  const fd = new FormData()
  fd.append("token", token)
  fd.append("file", file)
  return fetch(`http://127.0.0.1:8000/api/chats/${cid}/image`, { method: "POST", body: fd }).then(r => r.json())
}
export const confirmTask = (tid, user) => api(`/api/tasks/${tid}/confirm`, "POST", { user })
export const proposeTask = (tid, user, newContent) => api(`/api/tasks/${tid}/propose`, "POST", { user, new_content: newContent })
export const approveTask = (tid, user, approve) => api(`/api/tasks/${tid}/approve`, "POST", { user, approve })
export const getUserChats = (uid) => api(`/api/chats/user/${uid}`)

// 多 Agent
export const createAgent = (uid, roleType, name) => api(`/api/agents/${uid}/create`, "POST", { role_type: roleType, name })
export const splitTask = (title, detail, managerId) => api("/api/tasks/split", "POST", { title, detail, manager_agent_id: managerId })
export const pendingClassify = () => api("/api/tasks/pending-classify")
export const classifyTask = (tid, choice) => api(`/api/tasks/${tid}/classify`, "POST", { choice })
export const listAgents = () => api("/api/agents")
export const internalTasks = () => api("/api/tasks/internal")
export const estimatedTasks = () => api("/api/tasks/estimated")
export const distributeTask = (taskId, agentId) => api("/api/tasks/distribute", "POST", { task_id: taskId, agent_id: agentId })
export const estimateTask = (taskId, agentId) => api("/api/tasks/estimate", "POST", { task_id: taskId, agent_id: agentId })
export const reviewEstimate = (taskId, approve) => api(`/api/tasks/${taskId}/review-estimate`, "POST", { approve })
export const getRecords = (uid) => api(`/api/records/${uid}`)
export const saveRecords = (uid, content) => api(`/api/records/${uid}`, "POST", { content })
export const getCompany = (cid) => api(`/api/companies/${cid}`)
export const submitWork = (taskId, agentId, content) => api("/api/submissions/submit", "POST", { task_id: taskId, agent_id: agentId, content })
export const reviewSubmission = (sid, approve, exempt) => api(`/api/submissions/${sid}/review`, "POST", { approve, exempt })
export const setSalary = (uid, baseSalary, exempt) => api(`/api/salary/${uid}/set`, "POST", { base_salary: baseSalary, exempt })

// 查询接口（员工端 + 经理端）
export const getAgentByUser = (uid) => api(`/api/agents/user/${uid}`)
export const getMyTasks = (agentId) => api(`/api/tasks/agent/${agentId}`)
export const getSalary = (uid) => api(`/api/salary/${uid}`)
export const getPendingSubmissions = () => api("/api/submissions/pending")
export const getDashboardStats = () => api("/api/dashboard/stats")

// 工资结算 / 打款
export const getPayouts = () => api("/api/payouts")
export const payPayout = (pid) => api(`/api/payouts/${pid}/pay`, "POST", {})
export const getUserPayouts = (uid) => api(`/api/payouts/user/${uid}`)

// SaaS 套餐 / 订单 / 订阅
export const getPlans = () => api("/api/plans")
export const createOrder = (userId, planId) => api("/api/orders", "POST", { user_id: userId, plan_id: planId })
export const payOrder = (orderNo) => api(`/api/orders/${orderNo}/pay`, "POST", {})
export const getSubscription = (uid) => api(`/api/subscriptions/${uid}`)
