<template>
  <div class="agent">
    <h2>🤖 Agent</h2>
    <div class="msgs">
      <div v-for="(m, i) in msgs" :key="i" class="msg" :class="m.role">{{ m.content }}</div>
      <p v-if="!msgs.length" class="empty">和 Agent 对话，它可以查知识库、记住你的偏好</p>
    </div>
    <div class="input-bar">
      <input v-model="content" placeholder="和 Agent 对话..." @keyup.enter="send">
      <button @click="send">发送</button>
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue"
import { agentChat } from "./api.js"

const props = defineProps(["user"])
const content = ref(""), msgs = ref([])

async function send() {
  if (!content.value) return
  const q = content.value
  msgs.value.push({ role: "user", content: q })
  content.value = ""
  try {
    const r = await agentChat(q, props.user.id)
    msgs.value.push({ role: "ai", content: r.answer })
  } catch (e) {
    msgs.value.push({ role: "ai", content: "出错了：" + e.message })
  }
}
</script>

<style scoped>
.agent { max-width: 700px; margin: 0 auto; }
.msgs { height: 380px; overflow-y: auto; border: 1px solid #ddd; padding: 12px; margin-bottom: 8px; background: #fff; border-radius: 6px; }
.msg { padding: 8px; border-bottom: 1px solid #f0f0f0; white-space: pre-wrap; }
.msg.user { background: #eef2ff; }
.msg.ai { background: #f9fafb; }
.empty { color: #999; }
.input-bar { display: flex; gap: 8px; }
.input-bar input { flex: 1; padding: 8px; border: 1px solid #ddd; border-radius: 4px; }
.input-bar button { padding: 8px 16px; background: #2563eb; color: #fff; border: none; border-radius: 4px; }
</style>
