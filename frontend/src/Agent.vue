<template>
  <div class="agent">
    <div class="head">
      <h2>我的 Agent</h2>
      <p class="sub">它能查询团队知识库，也会记得你交代过的事情。</p>
    </div>
    <div class="msgs">
      <div v-for="(m, i) in msgs" :key="i" class="msg" :class="m.role">{{ m.content }}</div>
      <p v-if="!msgs.length" class="empty">输入内容，和你的 Agent 一起处理任务。</p>
    </div>
    <div class="input-bar">
      <input v-model="content" placeholder="输入内容，回车发送…" @keyup.enter="send">
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
.head { margin-bottom: 12px; }
.head h2 { margin: 0 0 4px; }
.sub { margin: 0; font-size: 13px; color: var(--muted); }
.msgs { height: 380px; overflow-y: auto; border: 1px solid var(--line); padding: 12px; margin-bottom: 8px; background: #fff; border-radius: 12px; }
.msg { padding: 8px; border-bottom: 1px solid #f0f0f0; white-space: pre-wrap; }
.msg.user { background: #eef2ff; }
.msg.ai { background: #f9fafb; }
.empty { color: #999; text-align: center; padding: 24px 0; }
.input-bar { display: flex; gap: 8px; }
.input-bar input { flex: 1; padding: 10px; border: 1px solid var(--line); border-radius: 10px; }
.input-bar button { padding: 10px 16px; background: var(--brand); color: #fff; border: none; border-radius: 10px; cursor: pointer; }
</style>
