<template>
  <Login v-if="!user" @logged-in="onLoggedIn" />
  <div v-else class="main">
    <header class="topbar">
      <div class="brand">
        <span class="brand-name">Scope Agent</span>
        <span class="role-tag" :class="user.role">{{ roleName(user.role) }}</span>
      </div>
      <div class="top-actions">
        <span class="who">你好，{{ user.name }}</span>
        <button class="logout" @click="logout">退出</button>
      </div>
    </header>

    <main class="content">
      <!-- 经理 -->
      <ManagerDash v-if="tab === 'work'" :user="user" @goto="goto" />
      <TaskCenter v-else-if="tab === 'task'" :user="user" />
      <ReviewSalary v-else-if="tab === 'review'" :user="user" />
      <AgentManage v-else-if="tab === 'agentmanage'" :user="user" />
      <Billing v-else-if="tab === 'billing'" :user="user" />

      <!-- 员工 / 普通成员 -->
      <MyTasks v-else-if="tab === 'mytask'" :user="user" />
      <Agent v-else-if="tab === 'agent'" :user="user" />
      <MySpace v-else-if="tab === 'mine'" :user="user" />
      <Project v-else-if="tab === 'project'" :user="user" />

      <!-- 消息 -->
      <ChatList v-else-if="tab === 'chat' && showList" :user="user" @open="openChat" />
      <Chat v-else-if="tab === 'chat'" :token="token" :user-id="user.id" :cid="currentChatId" @back="backToList" @read="refreshUnread" />

      <!-- 好友 -->
      <Friends v-else-if="tab === 'friends'" :user="user" />
    </main>

    <nav class="tabbar">
      <div
        v-for="t in navItems"
        :key="t.key"
        class="tab"
        :class="{ on: tab === t.key }"
        @click="goto(t.key)"
      >
        <el-badge v-if="t.key === 'chat'" :value="unreadTotal" :hidden="unreadTotal <= 0" :max="99" class="tab-badge">
          <span class="icon">{{ t.icon }}</span>
        </el-badge>
        <span v-else class="icon">{{ t.icon }}</span>
        <span class="label">{{ t.label }}</span>
      </div>
    </nav>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue"
import Login from "./Login.vue"
import Chat from "./Chat.vue"
import ChatList from "./ChatList.vue"
import Friends from "./Friends.vue"
import Project from "./Project.vue"
import Agent from "./Agent.vue"
import AgentManage from "./AgentManage.vue"
import TaskCenter from "./TaskCenter.vue"
import ReviewSalary from "./ReviewSalary.vue"
import ManagerDash from "./ManagerDash.vue"
import MySpace from "./MySpace.vue"
import MyTasks from "./MyTasks.vue"
import Billing from "./Billing.vue"
import { getUserChats } from "./api.js"

function roleName(r) { return r === "manager" ? "负责人" : r === "employee" ? "员工" : "成员" }

function navFor(role) {
  if (role === "manager") return [
    { key: "work", icon: "🏠", label: "工作台" },
    { key: "task", icon: "📋", label: "任务" },
    { key: "review", icon: "💰", label: "财务" },
    { key: "chat", icon: "💬", label: "消息" },
    { key: "friends", icon: "👥", label: "好友" },
  ]
  if (role === "employee") return [
    { key: "mytask", icon: "📋", label: "任务" },
    { key: "agent", icon: "🤖", label: "Agent" },
    { key: "chat", icon: "💬", label: "消息" },
    { key: "mine", icon: "👤", label: "我的" },
  ]
  // 普通成员
  return [
    { key: "chat", icon: "💬", label: "消息" },
    { key: "friends", icon: "👥", label: "好友" },
    { key: "project", icon: "📋", label: "项目" },
    { key: "mine", icon: "👤", label: "我的" },
  ]
}

function defaultTab(role) {
  if (role === "manager") return "work"
  if (role === "employee") return "mytask"
  return "chat"
}

const user = ref(null), token = ref(null), tab = ref("chat")
const currentChatId = ref(null), showList = ref(true), unreadTotal = ref(0)
const navItems = computed(() => navFor(user.value ? user.value.role : "user"))

const savedUser = localStorage.getItem("user")
const savedToken = localStorage.getItem("token")
if (savedUser && savedToken) {
  user.value = JSON.parse(savedUser)
  token.value = savedToken
  tab.value = defaultTab(user.value.role)
}

function onLoggedIn(u, t) {
  user.value = u; token.value = t
  localStorage.setItem("token", t)
  localStorage.setItem("user", JSON.stringify(u))
  tab.value = defaultTab(u.role)
  showList.value = true
  refreshUnread()
}

function logout() {
  user.value = null
  localStorage.removeItem("token")
  localStorage.removeItem("user")
  unreadTotal.value = 0
}

function openChat(id) {
  currentChatId.value = id
  showList.value = false
}
function backToList() {
  showList.value = true
  currentChatId.value = null
  refreshUnread()
}

function goto(key) {
  // 切到消息 tab 时回到会话列表；其它 tab 直接切换
  if (key === "chat" && tab.value === "chat" && !showList.value) backToList()
  tab.value = key
  if (key !== "chat") showList.value = true
}

async function refreshUnread() {
  if (!user.value) return
  try {
    const r = await getUserChats(user.value.id)
    unreadTotal.value = (r.chats || []).reduce((s, c) => s + (c.unread || 0), 0)
  } catch (e) { /* 忽略错误 */ }
}

onMounted(refreshUnread)
</script>

<style>
:root {
  --brand: #2563eb;
  --brand-soft: #eef2ff;
  --ink: #1f2329;
  --muted: #8a9099;
  --line: #eef0f3;
  --bg: #f5f6f8;
}
* { box-sizing: border-box; }
body { margin: 0; background: #e9ebef; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; color: var(--ink); }

.main { display: flex; flex-direction: column; height: 100vh; max-width: 520px; margin: 0 auto; background: #fff; }
@media (min-width: 560px) {
  .main { box-shadow: 0 0 0 1px #e4e7ec, 0 8px 40px rgba(0,0,0,.06); }
}

.topbar { display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; background: #fff; border-bottom: 1px solid var(--line); }
.brand { display: flex; align-items: center; gap: 8px; }
.brand-name { font-weight: 700; color: var(--brand); }
.role-tag { font-size: 11px; padding: 2px 8px; border-radius: 10px; background: var(--brand-soft); color: var(--brand); }
.role-tag.manager { background: #fdeaf0; color: #d6336c; }
.role-tag.employee { background: #e9f7ef; color: #2e9e5b; }
.top-actions { display: flex; align-items: center; gap: 10px; }
.who { font-size: 13px; color: var(--muted); }
.logout { border: none; background: transparent; color: var(--muted); cursor: pointer; font-size: 13px; }

.content { flex: 1; overflow-y: auto; padding: 16px; }

.tabbar { display: flex; background: #fff; border-top: 1px solid var(--line); padding-bottom: env(safe-area-inset-bottom); }
.tab { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 2px; padding: 8px 0 6px; cursor: pointer; color: #9aa1ab; }
.tab.on { color: var(--brand); }
.tab .icon { font-size: 20px; line-height: 1; }
.tab-badge { line-height: 1; }
.tab-badge .el-badge__content { transform: translateY(-2px); }
.tab .label { font-size: 11px; }

.manage-wrap { max-width: 720px; margin: 0 auto; }
</style>
