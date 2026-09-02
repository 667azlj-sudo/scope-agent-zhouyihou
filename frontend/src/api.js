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

export const register = (name, password, role) => api("/api/register", "POST", { name, password, role })
export const login = (name, password) => api("/api/login", "POST", { name, password })
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
