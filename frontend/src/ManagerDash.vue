<template>
  <div class="dash">
    <section class="hello">
      <div class="hello-name">你好，{{ user.name }}</div>
      <div class="hello-sub">这里是你的工作台，待办和团队进度都在这里</div>
    </section>

    <section v-if="company" class="company-card">
      <div class="company-left">
        <div class="company-name">{{ company.company.name }}</div>
        <div class="company-meta">{{ company.members.length }} 位成员</div>
      </div>
      <div class="company-right">
        <div class="code-label">邀请码</div>
        <div class="code-row">
          <span class="code">{{ company.company.invite_code }}</span>
          <el-button size="small" @click="copyCode">复制</el-button>
        </div>
      </div>
    </section>

    <section v-if="notifications.length" class="notif-card">
      <div class="notif-head">
        <span class="notif-title">通知</span>
        <el-button link type="primary" size="small" @click="readAll">全部已读</el-button>
      </div>
      <div v-for="n in notifications" :key="n.id" class="notif-item">
        <span :class="['dot', { unread: !n.is_read }]"></span>
        <span class="notif-text">{{ n.content }}</span>
      </div>
    </section>

    <section v-if="groupInvites.length" class="notif-card">
      <div class="notif-head"><span class="notif-title">加群申请（待我审核）</span></div>
      <div v-for="i in groupInvites" :key="i.id" class="invite-row">
        <span class="notif-text">{{ i.requester_name }} 想把 {{ i.target_name }} 加进「{{ i.chat_name || '群聊' }}」</span>
        <div class="invite-btns">
          <el-button size="small" type="success" @click="respondInvite(i.id, true)">同意</el-button>
          <el-button size="small" type="danger" plain @click="respondInvite(i.id, false)">拒绝</el-button>
        </div>
      </div>
    </section>

    <section class="stats">
      <div class="stat" @click="$emit('goto', 'task')">
        <div class="stat-num">{{ stats.pending_classify }}</div>
        <div class="stat-label">待分级任务</div>
      </div>
      <div class="stat" @click="$emit('goto', 'review')">
        <div class="stat-num">{{ stats.pending_submissions }}</div>
        <div class="stat-label">待审核提交</div>
      </div>
      <div class="stat">
        <div class="stat-num">{{ stats.team_agents }}</div>
        <div class="stat-label">团队 Agent</div>
      </div>
    </section>

    <section class="quick">
      <div class="quick-title">快捷操作</div>
      <div class="quick-grid">
        <button class="quick-card" @click="$emit('goto', 'task')">
          <span class="q-icon">📋</span>
          <span class="q-text">拆任务</span>
          <span class="q-desc">创建任务并自动分级</span>
        </button>
        <button class="quick-card" @click="$emit('goto', 'review')">
          <span class="q-icon">💰</span>
          <span class="q-text">财务</span>
          <span class="q-desc">审核成果、结算打款、设置工资</span>
        </button>
        <button class="quick-card" @click="$emit('goto', 'billing')">
          <span class="q-icon">📦</span>
          <span class="q-text">套餐订阅</span>
          <span class="q-desc">购买套餐解锁更多 Agent</span>
        </button>
        <button class="quick-card" @click="$emit('goto', 'conditions')">
          <span class="q-icon">📚</span>
          <span class="q-text">任务条件库</span>
          <span class="q-desc">维护各类任务需要的条件</span>
        </button>
        <button class="quick-card" @click="$emit('goto', 'agentmanage')">
          <span class="q-icon">🤖</span>
          <span class="q-text">Agent 管理</span>
          <span class="q-desc">为成员绑定专属 Agent</span>
        </button>
        <button class="quick-card" @click="$emit('goto', 'chat')">
          <span class="q-icon">💬</span>
          <span class="q-text">团队消息</span>
          <span class="q-desc">与成员保持沟通</span>
        </button>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue"
import { getDashboardStats, getCompany, getNotifications, readNotifications, getInvitesForManager, respondGroupInvite } from "./api.js"
import { ElMessage } from "element-plus"

const props = defineProps(["user"])
defineEmits(["goto"])
const stats = ref({ pending_classify: 0, pending_submissions: 0, team_agents: 0 })
const company = ref(null)
const notifications = ref([])
const groupInvites = ref([])

function copyCode() {
  if (!company.value) return
  navigator.clipboard?.writeText(company.value.company.invite_code)
  ElMessage.success("邀请码已复制")
}

async function readAll() {
  await readNotifications(props.user.id)
  notifications.value = notifications.value.map(n => ({ ...n, is_read: 1 }))
}

async function respondInvite(iid, ok) {
  const r = await respondGroupInvite(iid, props.user.id, ok, "manager")
  ElMessage.success(r.msg || (ok ? "已同意" : "已拒绝"))
  await loadInvites()
}

async function loadInvites() {
  try { groupInvites.value = (await getInvitesForManager()).invites || [] } catch (e) { /* 忽略 */ }
}

onMounted(async () => {
  try { stats.value = await getDashboardStats() } catch (e) { /* 忽略 */ }
  if (props.user.company_id) {
    try {
      const r = await getCompany(props.user.company_id)
      if (r.ok) company.value = r
    } catch (e) { /* 忽略 */ }
  }
  try { notifications.value = (await getNotifications(props.user.id)).notifications || [] } catch (e) { /* 忽略 */ }
  await loadInvites()
})
</script>

<style scoped>
.dash { max-width: 520px; margin: 0 auto; }
.hello { padding: 4px 2px 16px; }
.hello-name { font-size: 20px; font-weight: 700; }
.hello-sub { margin-top: 4px; font-size: 13px; color: var(--muted); }

.company-card { display: flex; justify-content: space-between; align-items: center; background: var(--brand-soft); border-radius: 14px; padding: 14px 16px; margin-bottom: 20px; }
.company-name { font-size: 16px; font-weight: 700; color: var(--brand); }
.company-meta { margin-top: 4px; font-size: 12px; color: var(--muted); }
.company-right { text-align: right; }
.code-label { font-size: 12px; color: var(--muted); }
.code-row { display: flex; align-items: center; gap: 8px; margin-top: 4px; }
.code { font-family: ui-monospace, Consolas, monospace; font-size: 16px; font-weight: 700; letter-spacing: 1px; }

.notif-card { background: #fff; border: 1px solid var(--line); border-radius: 14px; padding: 14px 16px; margin-bottom: 20px; }
.notif-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.notif-title { font-weight: 600; font-size: 14px; }
.notif-item { display: flex; align-items: flex-start; gap: 8px; padding: 6px 0; }
.dot { width: 7px; height: 7px; border-radius: 50%; background: #d1d5db; margin-top: 6px; flex-shrink: 0; }
.dot.unread { background: #f43f5e; }
.notif-text { font-size: 13px; color: #4b5158; }
.invite-row { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 8px 0; border-bottom: 1px solid var(--line); }
.invite-row:last-child { border-bottom: none; }
.invite-btns { display: flex; gap: 6px; flex-shrink: 0; }

.stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 24px; }
.stat { background: #fff; border: 1px solid var(--line); border-radius: 14px; padding: 16px 8px; text-align: center; cursor: pointer; transition: box-shadow .15s; }
.stat:hover { box-shadow: 0 4px 14px rgba(0,0,0,.06); }
.stat-num { font-size: 26px; font-weight: 700; color: var(--brand); }
.stat-label { margin-top: 4px; font-size: 12px; color: var(--muted); }

.quick-title { font-size: 14px; font-weight: 600; margin-bottom: 12px; }
.quick-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
.quick-card { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; padding: 16px; background: #fff; border: 1px solid var(--line); border-radius: 14px; text-align: left; cursor: pointer; transition: box-shadow .15s; }
.quick-card:hover { box-shadow: 0 4px 14px rgba(0,0,0,.06); }
.q-icon { font-size: 22px; }
.q-text { font-size: 15px; font-weight: 600; }
.q-desc { font-size: 12px; color: var(--muted); }
</style>
