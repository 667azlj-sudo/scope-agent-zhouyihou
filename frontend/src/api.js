// src/api.js —— 后端 API 封装（走相对路径，由 Vite 代理转发到后端）
const BASE = ""

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
  return fetch(`/api/chats/${cid}/image`, { method: "POST", body: fd }).then(r => r.json())
}
export const confirmTask = (tid, user) => api(`/api/tasks/${tid}/confirm`, "POST", { user })
export const proposeTask = (tid, user, newContent) => api(`/api/tasks/${tid}/propose`, "POST", { user, new_content: newContent })
export const approveTask = (tid, user, approve) => api(`/api/tasks/${tid}/approve`, "POST", { user, approve })
export const getUserChats = (uid) => api(`/api/chats/user/${uid}`)

// 多 Agent
export const createAgent = (uid, roleType, name) => api(`/api/agents/${uid}/create`, "POST", { role_type: roleType, name })
export const splitTask = (title, detail, managerId) => api("/api/tasks/split", "POST", { title, detail, manager_agent_id: managerId })
export function uploadTaskFile(file) {
  const fd = new FormData()
  fd.append("file", file)
  return fetch(`/api/tasks/file`, { method: "POST", body: fd }).then(r => r.json())
}
export const pendingClassify = () => api("/api/tasks/pending-classify")
export const classifyTask = (tid, choice) => api(`/api/tasks/${tid}/classify`, "POST", { choice })
export const listAgents = () => api("/api/agents")
export const internalTasks = () => api("/api/tasks/internal")
export const estimatedTasks = () => api("/api/tasks/estimated")
export const distributeTask = (taskId, agentId) => api("/api/tasks/distribute", "POST", { task_id: taskId, agent_id: agentId })
export const estimateTask = (taskId, agentId) => api("/api/tasks/estimate", "POST", { task_id: taskId, agent_id: agentId })
export const reviewEstimate = (taskId, approve, customWage) => api(`/api/tasks/${taskId}/review-estimate`, "POST", { approve, custom_wage: customWage })
export const getRecords = (uid) => api(`/api/records/${uid}`)
export const saveRecords = (uid, content) => api(`/api/records/${uid}`, "POST", { content })
export const getCompany = (cid) => api(`/api/companies/${cid}`)
export const getUsers = () => api("/api/users")

// 任务大厅
export const unmatchedTasks = () => api("/api/tasks/unmatched")
export const publishToHall = (taskId, candidateIds) => api(`/api/tasks/${taskId}/publish-hall`, "POST", { candidate_ids: candidateIds })
export const getHallTasks = (uid) => api(`/api/hall/${uid}`)
export const claimTask = (taskId, userId) => api(`/api/hall/${taskId}/claim`, "POST", { user_id: userId })

// 外包大厅
export const getOutsourceTasks = () => api("/api/outsource")
export const acceptOutsource = (taskId, userId) => api(`/api/outsource/${taskId}/accept`, "POST", { user_id: userId })

// 知识库① 工作记录
export const getWorkRecords = (uid) => api(`/api/records/work/${uid}`)
export const addWorkRecord = (uid, content) => api(`/api/records/work/${uid}`, "POST", { content })
export const deleteWorkRecord = (rid) => api(`/api/records/work/${rid}`, "DELETE", {})
export const importWorkRecordsFromChats = (uid) => api(`/api/records/work/${uid}/from-chats`, "POST", {})
export function uploadWorkRecordFile(uid, file) {
  const fd = new FormData()
  fd.append("file", file)
  return fetch(`/api/records/work/${uid}/upload`, { method: "POST", body: fd }).then(r => r.json())
}

// 个人能力知识库（读取电脑 → RAG）
export const getAbilityStats = (uid) => api(`/api/knowledge/${uid}/stats`)
export function uploadAbilityFiles(uid, files) {
  const fd = new FormData()
  for (const f of files) fd.append("files", f)
  return fetch(`/api/knowledge/${uid}/upload`, { method: "POST", body: fd }).then(r => r.json())
}

// 知识库② 任务条件
export const getTaskConditions = (companyId) => api(`/api/conditions/${companyId}`)
export const addTaskCondition = (companyId, keywords, conditions) => api("/api/conditions", "POST", { company_id: companyId, keywords, conditions })
export const deleteTaskCondition = (cid) => api(`/api/conditions/${cid}`, "DELETE", {})

// 通知
export const getNotifications = (uid) => api(`/api/notifications/${uid}`)
export const readNotifications = (uid) => api(`/api/notifications/${uid}/read`, "POST", {})

// 群聊
export const createGroup = (name, memberIds) => api("/api/chats/group", "POST", { name, member_ids: memberIds })
export const getChatMembers = (cid) => api(`/api/chats/${cid}/members`)
export const addChatMember = (cid, userId) => api(`/api/chats/${cid}/members`, "POST", { user_id: userId })
export const createGroupInvite = (cid, requesterId, targetId) => api(`/api/chats/${cid}/invite`, "POST", { requester_id: requesterId, target_id: targetId })
export const getInvitesForTarget = (uid) => api(`/api/invites/target/${uid}`)
export const getInvitesForManager = () => api("/api/invites/manager")
export const respondGroupInvite = (iid, userId, approve, role) => api(`/api/invites/${iid}/respond`, "POST", { user_id: userId, approve, role })
export const submitWork = (taskId, agentId, content, images) => api("/api/submissions/submit", "POST", { task_id: taskId, agent_id: agentId, content, images: images || [] })
export const markChatRead = (cid, token) => api(`/api/chats/${cid}/read`, "POST", { token })
export function uploadSubmissionImage(file) {
  const fd = new FormData()
  fd.append("file", file)
  return fetch(`/api/submissions/image`, { method: "POST", body: fd }).then(r => r.json())
}
export const reviewSubmission = (sid, approve, exempt, customPrice) => api(`/api/submissions/${sid}/review`, "POST", { approve, exempt, custom_price: customPrice })
export const setSalary = (uid, baseSalary, exempt) => api(`/api/salary/${uid}/set`, "POST", { base_salary: baseSalary, exempt })

// 权责审核流水线
export const agentCheck = (sid) => api(`/api/submissions/${sid}/agent-check`, "POST", {})
export const managerTest = (sid) => api(`/api/submissions/${sid}/manager-test`, "POST", {})
export const managerVerify = (sid, approve, customPrice) => api(`/api/submissions/${sid}/manager-verify`, "POST", { approve, custom_price: customPrice })
export const designateTech = (sid, userId) => api(`/api/submissions/${sid}/designate-tech`, "POST", { user_id: userId })
export const techVerify = (sid, userId, approve) => api(`/api/submissions/${sid}/tech-verify`, "POST", { user_id: userId, approve })

// 工资发放方式
export const getPayMode = (cid) => api(`/api/company/${cid}/pay-mode`)
export const setPayMode = (cid, payMode) => api(`/api/company/${cid}/pay-mode`, "POST", { pay_mode: payMode })
export const payAllPayouts = () => api("/api/payouts/pay-all", "POST", {})

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
