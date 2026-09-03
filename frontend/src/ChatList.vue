<template>
  <div class="chat-list">
    <div class="chat-list-toolbar">
      <el-button type="primary" @click="openCreate">＋ 建群</el-button>
    </div>

    <div
      v-for="chat in chats"
      :key="chat.id"
      class="chat-item"
      @click="$emit('open', chat.id)"
    >
      <el-badge :value="chat.unread" :hidden="!chat.unread || chat.unread <= 0" :max="99" class="avatar-badge">
        <el-avatar :size="44" class="chat-avatar">{{ avatarOf(chat) }}</el-avatar>
      </el-badge>
      <div class="chat-info">
        <div class="chat-name-row">
          <span class="chat-name">{{ nameOf(chat) }}</span>
          <span class="chat-type" :class="chat.type">{{ typeLabel(chat.type) }}</span>
        </div>
        <div class="chat-preview">{{ chat.last_msg || "" }}</div>
      </div>
      <el-button
        v-if="chat.type !== 'direct' && user.role === 'manager'"
        link type="primary" size="small" class="pull-btn"
        @click.stop="openAddMember(chat)"
      >拉人</el-button>
    </div>
    <p v-if="!chats.length" class="empty">暂无会话</p>

    <!-- 建群 -->
    <el-dialog v-model="dialogVisible" title="创建群聊" width="92%">
      <el-input v-model="newGroupName" placeholder="请输入群名" class="mb" />
      <div class="member-pick">
        <div class="pick-title">选择成员（多选）</div>
        <el-checkbox-group v-model="selectedMembers">
          <el-checkbox v-for="m in otherMembers" :key="m.id" :value="m.id">{{ m.name }}{{ m.position ? " · " + m.position : "" }}</el-checkbox>
        </el-checkbox-group>
      </div>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="doCreateGroup">创建</el-button>
      </template>
    </el-dialog>

    <!-- 拉人 -->
    <el-dialog v-model="addMemberVisible" title="拉人进群" width="92%">
      <div class="pick-title">选择要拉进的成员</div>
      <el-select v-model="addMemberUserId" placeholder="选择成员" style="width: 100%">
        <el-option v-for="m in otherMembers" :key="m.id" :label="m.name + (m.position ? ' · ' + m.position : '')" :value="m.id" />
      </el-select>
      <template #footer>
        <el-button @click="addMemberVisible = false">取消</el-button>
        <el-button type="primary" @click="doAddMember">拉入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue"
import { getUserChats, createGroup, addChatMember, getCompany } from "./api.js"
import { ElMessage } from "element-plus"

const props = defineProps(["user"])
const emit = defineEmits(["open"])
const chats = ref([])
const companyMembers = ref([])
const dialogVisible = ref(false), newGroupName = ref(""), selectedMembers = ref([])
const addMemberVisible = ref(false), addMemberChatId = ref(null), addMemberUserId = ref(null)

const otherMembers = computed(() => companyMembers.value.filter(m => m.id !== props.user.id))

function typeLabel(t) { return t === "company" ? "总公司" : t === "group" ? "群聊" : "私聊" }
function nameOf(c) { return c.type === "company" ? "总公司群" : (c.name || "私聊") }
function avatarOf(c) { return (nameOf(c) || "?")[0] }

onMounted(async () => {
  await loadChats()
  if (props.user.company_id) {
    try {
      const r = await getCompany(props.user.company_id)
      if (r.ok) companyMembers.value = r.members || []
    } catch (e) { /* 忽略 */ }
  }
})

async function loadChats() {
  const r = await getUserChats(props.user.id)
  chats.value = r.chats || []
}

function openCreate() {
  newGroupName.value = ""
  selectedMembers.value = []
  dialogVisible.value = true
}

async function doCreateGroup() {
  const name = newGroupName.value.trim()
  if (!name) { ElMessage.warning("请输入群名"); return }
  const ids = [props.user.id, ...selectedMembers.value]
  try {
    const r = await createGroup(name, ids)
    if (!r.ok || !r.chat_id) { ElMessage.error(r.msg || "创建失败"); return }
    dialogVisible.value = false
    await loadChats()
    emit("open", r.chat_id)
  } catch (e) {
    ElMessage.error("创建失败")
  }
}

function openAddMember(chat) {
  addMemberChatId.value = chat.id
  addMemberUserId.value = null
  addMemberVisible.value = true
}

async function doAddMember() {
  if (!addMemberUserId.value) { ElMessage.warning("请选择成员"); return }
  try {
    await addChatMember(addMemberChatId.value, addMemberUserId.value)
    ElMessage.success("已拉入群聊")
    addMemberVisible.value = false
  } catch (e) {
    ElMessage.error("拉人失败")
  }
}
</script>

<style scoped>
.chat-list { max-width: 700px; margin: 0 auto; }
.chat-list-toolbar { display: flex; justify-content: flex-end; padding: 4px 0 12px; }
.chat-item { display: flex; align-items: center; gap: 12px; padding: 12px 8px; border-bottom: 1px solid #f0f0f0; cursor: pointer; transition: background 0.2s; }
.chat-item:hover { background: #f5f5f5; }
.avatar-badge { flex-shrink: 0; }
.chat-avatar { background: #2563eb; color: #fff; }
.chat-info { flex: 1; min-width: 0; }
.chat-name-row { display: flex; align-items: center; gap: 6px; }
.chat-name { font-size: 15px; font-weight: 500; color: #222; }
.chat-type { font-size: 11px; padding: 1px 6px; border-radius: 8px; background: #eef2ff; color: var(--brand); }
.chat-type.company { background: #e9f7ef; color: #2e9e5b; }
.chat-type.direct { background: #f1f2f4; color: #8a9099; }
.chat-preview { margin-top: 3px; font-size: 13px; color: #999; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pull-btn { flex-shrink: 0; }
.empty { color: #999; text-align: center; padding: 24px 0; }
.mb { margin-bottom: 12px; }
.pick-title { font-size: 13px; color: var(--muted); margin-bottom: 8px; }
.member-pick .el-checkbox { display: block; margin-right: 0; margin-bottom: 6px; }
</style>
