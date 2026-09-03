<template>
  <div class="chat">
    <div v-if="cid" class="chat-header">
      <el-button link type="primary" @click="$emit('back')">← 返回列表</el-button>
    </div>
    <template v-if="cid">
      <div class="msgs" ref="msgsRef">
        <div v-for="m in messages" :key="m.id" class="msg-row" :class="{ mine: m.sender_id === userId }">
          <div class="avatar">{{ (m.sender_name || "?")[0] }}</div>
          <div class="bubble-wrap">
            <div v-if="m.sender_id !== userId" class="name">{{ m.sender_name }}</div>
            <div class="bubble" :class="{ min: m.sender_id === userId }">
              <template v-if="m.status === 'withdrawn'"><span class="withdrawn">🚫 一条消息被撤回</span></template>
              <template v-else-if="m.type === 'location'">📍 {{ m.lat }}, {{ m.lng }}</template>
              <template v-else-if="m.type === 'image'"><img :src="m.content" class="msg-img" /></template>
              <template v-else>{{ m.content }}</template>
            </div>
            <el-button
              v-if="m.sender_id === userId && m.status !== 'withdrawn'"
              link type="primary" size="small" @click="withdraw(m)">撤回</el-button>
          </div>
        </div>
        <p v-if="!messages.length" class="empty">还没有消息</p>
      </div>
      <div class="input-bar">
        <el-input v-model="content" placeholder="输入消息..." @keyup.enter="send" />
        <el-button type="primary" @click="send">发送</el-button>
        <el-button @click="sendLocation">📍</el-button>
        <el-button @click="fileInput.click()">🖼</el-button>
        <input ref="fileInput" type="file" accept="image/*" hidden @change="sendImageFile" />
      </div>
    </template>
    <p v-else class="no-chat">没有会话</p>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from "vue"
import { sendMessage, getMessages, withdrawMessage, sendImage, markChatRead } from "./api.js"

const props = defineProps(["token", "userId", "cid"])
const emit = defineEmits(["back", "read"])
const messages = ref([]), content = ref(""), chatId = ref(null), msgsRef = ref(null), fileInput = ref(null)

onMounted(async () => {
  if (props.cid) {
    chatId.value = props.cid
    await load()
  }
})

async function load() {
  const r = await getMessages(chatId.value)
  messages.value = r.messages || []
  // 打开即已读，消除红点
  try { await markChatRead(chatId.value, props.token); emit("read") } catch (e) { /* 忽略 */ }
  await nextTick()
  if (msgsRef.value) msgsRef.value.scrollTop = msgsRef.value.scrollHeight
}

async function send() {
  if (!content.value) return
  await sendMessage(chatId.value, props.token, content.value)
  content.value = ""
  await load()
}

async function withdraw(m) {
  await withdrawMessage(m.id, props.token)
  await load()
}

async function sendLocation() {
  const pos = await new Promise((resolve, reject) => navigator.geolocation.getCurrentPosition(resolve, reject))
  await sendMessage(chatId.value, props.token, "位置", "location", pos.coords.latitude, pos.coords.longitude)
  await load()
}

async function sendImageFile(e) {
  const f = e.target.files[0]
  if (!f) return
  await sendImage(chatId.value, props.token, f)
  e.target.value = ""
  await load()
}
</script>

<style scoped>
.chat { max-width: 700px; margin: 0 auto; }
.chat-header { padding-bottom: 8px; }
.msgs { height: 420px; overflow-y: auto; padding: 16px; background: #f5f5f5; border-radius: 8px; margin-bottom: 12px; }
.msg-row { display: flex; gap: 8px; margin-bottom: 14px; }
.msg-row.mine { flex-direction: row-reverse; }
.avatar { width: 36px; height: 36px; border-radius: 50%; background: #2563eb; color: #fff; display: flex; justify-content: center; align-items: center; flex-shrink: 0; }
.msg-row.mine .avatar { background: #16a34a; }
.bubble-wrap { max-width: 70%; }
.name { font-size: 12px; color: #999; margin-bottom: 2px; }
.bubble { padding: 8px 12px; border-radius: 8px; background: #fff; box-shadow: 0 1px 2px rgba(0,0,0,.05); white-space: pre-wrap; word-break: break-word; }
.bubble.min { background: #95ec69; }
.msg-img { max-width: 220px; border-radius: 8px; display: block; }
.withdrawn { color: #999; font-style: italic; font-size: 13px; }
.empty { color: #999; }
.no-chat { color: #999; text-align: center; padding: 48px 0; }
.input-bar { display: flex; gap: 8px; }
</style>
