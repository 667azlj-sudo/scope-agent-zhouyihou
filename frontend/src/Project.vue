<template>
  <div class="project">
    <h2>📋 项目</h2>

    <div class="create">
      <input v-model="desc" placeholder="输入项目描述，如：开发一个企业官网">
      <button @click="create">AI 拆解</button>
    </div>

    <div v-if="projectId" class="tasks">
      <div class="stats">自动分配 {{ stats.auto }} 个 / 待确认 {{ stats.pending }} 个</div>
      <div v-for="t in tasks" :key="t.id" class="task">
        <div class="task-main">
          <span class="content">{{ t.content }}</span>
          <span class="tag" :class="t.type">{{ t.type }}</span>
          <span class="status">{{ t.status }}</span>
        </div>
        <button v-if="user.role === 'manager' && t.status === 'pending_review'" @click="confirm(t)">确认</button>
        <button v-if="user.role === 'manager' && t.status === 'negotiating'" @click="approve(t)">审批</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue"
import { createProject, getTasks, confirmTask, approveTask } from "./api.js"

const props = defineProps(["user"])
const desc = ref(""), projectId = ref(null), tasks = ref([]), stats = ref({ auto: 0, pending: 0 })

async function create() {
  if (!desc.value) return
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
.create { display: flex; gap: 8px; margin-bottom: 20px; }
.create input { flex: 1; padding: 8px; border: 1px solid #ddd; border-radius: 4px; }
.create button { padding: 8px 16px; background: #2563eb; color: #fff; border: none; border-radius: 4px; cursor: pointer; }
.stats { margin-bottom: 12px; color: #666; }
.task { display: flex; justify-content: space-between; align-items: center; padding: 10px; border-bottom: 1px solid #eee; }
.task-main { display: flex; gap: 8px; align-items: center; }
.tag { padding: 2px 8px; border-radius: 4px; font-size: 12px; }
.tag.简单 { background: #d1fae5; color: #065f46; }
.tag.模糊 { background: #fef3c7; color: #92400e; }
.status { color: #888; font-size: 13px; }
</style>
