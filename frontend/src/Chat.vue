<template>
  <div class="chat">
    <div v-if="cid" class="chat-header">
      <el-button link type="primary" @click="$emit('back')">← 返回列表</el-button>
      <div class="chat-header-right">
        <el-button link type="primary" size="small" @click="membersVisible = true">成员</el-button>
      </div>
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
              <template v-else>
                <span v-for="(seg, i) in parseMentions(m.content)" :key="i" :class="{ at: seg.mention }">{{ seg.text }}</span>
              </template>
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
        <el-button @click="mentionVisible = true">@</el-button>
        <el-button @click="sendLocation">📍</el-button>
        <el-button @click="fileInput.click()">🖼</el-button>
        <input ref="fileInput" type="file" accept="image/*" hidden @change="sendImageFile" />
      </div>

      <el-dialog v-model="mentionVisible" title="选择要 @ 的人" width="92%">
        <div v-for="m in members" :key="m.id" class="mention-item" @click="mention(m)">
          {{ m.name }}{{ m.position ? " · " + m.position : "" }}
        </div>
        <p v-if="!members.length" class="empty">暂无成员</p>
      </el-dialog>

      <el-dialog v-model="membersVisible" title="群成员" width="92%">
        <div v-for="m in members" :key="m.id" class="mention-item">
          {{ m.name }}{{ m.position ? " · " + m.position : "" }}
          <el-tag size="small" :type="m.role === 'manager' ? 'danger' : 'info'" effect="plain">{{ m.role === 'manager' ? '负责人' : '成员' }}</el-tag>
        </div>
        <p v-if="!members.length" class="empty">暂无成员</p>

        <div class="add-member-area">
          <div class="pick-title">{{ role === 'manager' ? '经理可直接拉人进群' : '加人需对方和经理审核通过' }}</div>
          <div class="add-member-row">
            <el-select v-model="addTargetId" placeholder="选择要加的人" style="flex: 1">
              <el-option v-for="u in addableUsers" :key="u.id" :label="u.name + (u.position ? ' · ' + u.position : '')" :value="u.id" />
            </el-select>
            <el-button type="primary" @click="doAddMember">{{ role === 'manager' ? '拉入群聊' : '发起申请' }}</el-button>
          </div>
        </div>
      </el-dialog>
    </template>
    <p v-else class="no-chat">没有会话</p>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from "vue"
import { sendMessage, getMessages, withdrawMessage, sendImage, markChatRead, getChatMembers, getUsers, createGroupInvite, addChatMember } from "./api.js"
import { ElMessage } from "element-plus"

const props = defineProps(["token", "userId", "role", "cid"])
const emit = defineEmits(["back", "read"])
const messages = ref([]), content = ref(""), chatId = ref(null), msgsRef = ref(null), fileInput = ref(null)
const members = ref([]), mentionVisible = ref(false)
const membersVisible = ref(false), allUsers = ref([]), addTargetId = ref(null)

const addableUsers = computed(() => {
  const inGroup = new Set(members.value.map(m => m.id))
  return allUsers.value.filter(u => u.id !== props.userId && !inGroup.has(u.id))
})

onMounted(async () => {
  if (props.cid) {
    chatId.value = props.cid
    await load()
  }
})

async function load() {
  const r = await getMessages(chatId.value)
  messages.value = r.messages || []
  // 拉群成员（@ / 查看 / 加人用）
  try { members.value = (await getChatMembers(chatId.value)).members || [] } catch (e) { /* 忽略 */ }
  try { allUsers.value = (await getUsers()).users || [] } catch (e) { /* 忽略 */ }
  // 打开即已读，消除红点
  try { await markChatRead(chatId.value, props.token); emit("read") } catch (e) { /* 忽略 */ }
  await nextTick()
  if (msgsRef.value) msgsRef.value.scrollTop = msgsRef.value.scrollHeight
}

async function doAddMember() {
  if (!addTargetId.value) { ElMessage.warning("请选择要加的人"); return }
  try {
    if (props.role === 'manager') {
      // 经理直接拉入
      await addChatMember(chatId.value, addTargetId.value)
      ElMessage.success("已拉入群聊")
    } else {
      // 员工发起申请（需对方 + 经理审核）
      const r = await createGroupInvite(chatId.value, props.userId, addTargetId.value)
      if (r.ok) ElMessage.success("已发起申请，等待对方和经理审核")
      else ElMessage.error(r.msg || "发起失败")
    }
    addTargetId.value = null
    await load()
  } catch (e) {
    ElMessage.error("操作失败")
  }
}

function mention(m) {
  content.value = (content.value ? content.value.replace(/\s*$/, "") + " " : "") + "@" + m.name + " "
  mentionVisible.value = false
}

function parseMentions(text) {
  return (text || "").split(/(@[^\s@，。]+)/g).filter(Boolean).map(part => ({
    text: part,
    mention: part.startsWith("@"),
  }))
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
.chat-header { display: flex; align-items: center; padding-bottom: 8px; }
.chat-header-right { margin-left: auto; display: flex; gap: 4px; }
.pick-title { font-size: 13px; color: var(--muted); margin-bottom: 8px; }
.add-member-area { margin-top: 12px; padding-top: 12px; border-top: 1px dashed var(--line); }
.add-member-row { display: flex; gap: 8px; }
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
.at { color: var(--brand); font-weight: 600; }
.mention-item { padding: 10px 4px; border-bottom: 1px solid #f0f0f0; cursor: pointer; }
.mention-item:hover { background: #f5f5f5; }
.empty { color: #999; }
.no-chat { color: #999; text-align: center; padding: 48px 0; }
.input-bar { display: flex; gap: 8px; }
</style>
