<template>
  <div class="project">
    <div class="head">
      <h2>项目</h2>
      <p class="sub">描述一个目标，系统会拆出可执行的事项，并与团队协作推进。</p>
    </div>

    <div class="create">
      <input v-model="desc" placeholder="例如：做一个企业官网" @keyup.enter="create">
      <button @click="create">拆解</button>
    </div>

    <div v-if="projectId" class="tasks">
      <div class="stats">已自动分配 {{ stats.auto }} 项 · 待确认 {{ stats.pending }} 项</div>
      <div v-for="t in tasks" :key="t.id" class="task">
        <div class="task-main">
          <span class="content">{{ t.content }}</span>
          <span class="tag" :class="t.type">{{ t.type }}</span>
          <span class="status">{{ statusLabel(t.status) }}</span>
        </div>
        <button v-if="user.role === 'manager' && t.status === 'pending_review'" @click="confirm(t)">确认</button>
        <button v-if="user.role === 'manager' && t.status === 'negotiating'" @click="approve(t)">审批</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue"
import { ElMessage } from "element-plus"
import { createProject, getTasks, confirmTask, approveTask } from "./api.js"
import { statusLabel } from "./format.js"

const props = defineProps(["user"])
const desc = ref(""), projectId = ref(null), tasks = ref([]), stats = ref({ auto: 0, pending: 0 })

async function create() {
  if (!desc.value) { ElMessage.warning("请先描述项目"); return }
  const r = await createProject(desc.value)
  projectId.value = r.project_id
  stats.value = { auto: r.auto_assigned, pending: r.pending_review }
  await load()
}

async function load() {
  tasks.value = (await getTasks(projectId.value)).tasks || []
}

async function confirm(t) {
  await confirmTask(t.id, props.user.name)
  await load()
}

async function approve(t) {
  await approveTask(t.id, props.user.name, true)
  await load()
}
</script>

<style scoped>
.project { max-width: 520px; margin: 0 auto; }
.head { margin-bottom: 14px; }
.head h2 { margin: 0 0 4px; }
.sub { margin: 0; font-size: 13px; color: var(--muted); }
.create { display: flex; gap: 8px; margin-bottom: 20px; }
.create input { flex: 1; padding: 10px; border: 1px solid var(--line); border-radius: 10px; }
.create button { padding: 10px 16px; background: var(--brand); color: #fff; border: none; border-radius: 10px; cursor: pointer; }
.stats { margin-bottom: 12px; color: var(--muted); font-size: 13px; }
.task { display: flex; justify-content: space-between; align-items: center; padding: 12px 0; border-bottom: 1px solid var(--line); }
.task-main { display: flex; gap: 8px; align-items: center; min-width: 0; }
.content { font-size: 14px; }
.tag { padding: 2px 8px; border-radius: 10px; font-size: 12px; }
.tag.简单 { background: #e9f7ef; color: #2e9e5b; }
.tag.模糊 { background: #fff6e6; color: #b7791f; }
.status { color: var(--muted); font-size: 13px; }
</style>
