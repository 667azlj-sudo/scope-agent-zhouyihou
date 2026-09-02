<template>
  <div class="chat-list">
    <div
      v-for="chat in chats"
      :key="chat.id"
      class="chat-item"
      @click="$emit('open', chat.id)"
    >
      <el-badge :value="chat.unread" :hidden="!chat.unread || chat.unread <= 0" :max="99" class="avatar-badge">
        <el-avatar :size="44" class="chat-avatar">{{ (chat.name || "?")[0] }}</el-avatar>
      </el-badge>
      <div class="chat-info">
        <div class="chat-name">{{ chat.name }}</div>
        <div class="chat-preview">{{ chat.last_msg || "" }}</div>
      </div>
    </div>
    <p v-if="!chats.length" class="empty">暂无会话</p>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue"
import { getUserChats } from "./api.js"

const props = defineProps(["user"])
const emit = defineEmits(["open"])
const chats = ref([])

onMounted(async () => {
  if (!props.user) return
  const r = await getUserChats(props.user.id)
  chats.value = r.chats || []
})
</script>

<style scoped>
.chat-list { max-width: 700px; margin: 0 auto; }
.chat-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 8px;
  border-bottom: 1px solid #f0f0f0;
  cursor: pointer;
  transition: background 0.2s;
}
.chat-item:hover { background: #f5f5f5; }
.avatar-badge { flex-shrink: 0; }
.chat-avatar { background: #2563eb; color: #fff; }
.chat-info { flex: 1; min-width: 0; }
.chat-name { font-size: 15px; font-weight: 500; color: #222; }
.chat-preview {
  margin-top: 3px;
  font-size: 13px;
  color: #999;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.empty { color: #999; text-align: center; padding: 24px 0; }
</style>
