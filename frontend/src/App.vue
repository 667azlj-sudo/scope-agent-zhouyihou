<template>
  <div class="app">
    <Login v-if="!user" @logged-in="onLoggedIn" />
    <div v-else class="main">
      <div class="topbar">
        <span class="brand">Scope Agent</span>
        <button class="logout" @click="logout">退出 {{ user.name }}</button>
      </div>
      <div class="content">
        <div v-if="tab === 'chat'">
          <ChatList v-if="showList" :user="user" @open="openChat" />
          <Chat v-else :token="token" :user-id="user.id" :cid="currentChatId" @back="backToList" />
        </div>
        <Friends v-else-if="tab === 'friends'" :user="user" />
        <Project v-else-if="tab === 'project'" :user="user" />
        <Agent v-else-if="tab === 'agent'" :user="user" />
      </div>
      <nav class="tabbar">
        <div v-for="t in tabs" :key="t.key" class="tab" :class="{ on: tab === t.key }" @click="onTab(t.key)">
          <el-badge v-if="t.key === 'chat'" :value="unreadTotal" :hidden="unreadTotal <= 0" :max="99" class="tab-badge">
            <span class="icon">{{ t.icon }}</span>
          </el-badge>
          <span v-else class="icon">{{ t.icon }}</span>
          <span class="label">{{ t.label }}</span>
        </div>
      </nav>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue"
import Login from "./Login.vue"
import Chat from "./Chat.vue"
import ChatList from "./ChatList.vue"
import Friends from "./Friends.vue"
import Project from "./Project.vue"
import Agent from "./Agent.vue"
import { getUserChats } from "./api.js"

const tabs = [
  { key: "chat", icon: "💬", label: "聊天" },
  { key: "friends", icon: "👥", label: "好友" },
  { key: "project", icon: "📋", label: "项目" },
  { key: "agent", icon: "🤖", label: "Agent" },
]

const user = ref(null), token = ref(null), tab = ref("chat")
const currentChatId = ref(null), showList = ref(true), unreadTotal = ref(0)
const savedUser = localStorage.getItem("user")
const savedToken = localStorage.getItem("token")
if (savedUser && savedToken) {
  user.value = JSON.parse(savedUser)
  token.value = savedToken
}
function onLoggedIn(u, t) {
  user.value = u; token.value = t
  localStorage.setItem("token", t)
  localStorage.setItem("user", JSON.stringify(u))
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
function onTab(key) {
  if (key === "chat" && tab.value === "chat" && !showList.value) backToList()
  tab.value = key
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
body { font-family: sans-serif; margin: 0; background: #f5f7fa; }
.main { display: flex; flex-direction: column; height: 100vh; }
.topbar { display: flex; justify-content: space-between; align-items: center; padding: 10px 16px; background: #fff; border-bottom: 1px solid #eee; }
.brand { font-weight: bold; color: #2563eb; }
.logout { border: none; background: none; color: #999; cursor: pointer; }
.content { flex: 1; overflow-y: auto; padding: 16px; }
.tabbar { display: flex; background: #fff; border-top: 1px solid #eee; }
.tab { flex: 1; display: flex; flex-direction: column; align-items: center; padding: 8px 0; cursor: pointer; color: #999; }
.tab.on { color: #2563eb; }
.tab .icon { font-size: 20px; }
.tab-badge { line-height: 1; }
.tab-badge .el-badge__content { transform: translateY(-2px); }
.tab .label { font-size: 12px; }
</style>
