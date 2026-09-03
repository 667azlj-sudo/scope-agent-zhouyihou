<template>
  <div class="dash">
    <section class="hello">
      <div class="hello-name">你好，{{ user.name }}</div>
      <div class="hello-sub">这里是你的工作台，待办和团队进度都在这里</div>
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
          <span class="q-icon">✅</span>
          <span class="q-text">审核提交</span>
          <span class="q-desc">查看员工提交的成果</span>
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
import { getDashboardStats } from "./api.js"

const props = defineProps(["user"])
defineEmits(["goto"])
const stats = ref({ pending_classify: 0, pending_submissions: 0, team_agents: 0 })

onMounted(async () => {
  try { stats.value = await getDashboardStats() } catch (e) { /* 忽略 */ }
})
</script>

<style scoped>
.dash { max-width: 520px; margin: 0 auto; }
.hello { padding: 4px 2px 16px; }
.hello-name { font-size: 20px; font-weight: 700; }
.hello-sub { margin-top: 4px; font-size: 13px; color: var(--muted); }

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
