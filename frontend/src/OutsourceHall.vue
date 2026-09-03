<template>
  <div class="outsource-hall">
    <div class="head">
      <h2>外包大厅</h2>
      <p class="sub">其他公司发布的外包任务，接取后由你的 Agent 报价、审核、完成。</p>
    </div>

    <div v-for="t in tasks" :key="t.id" class="task-card">
      <div class="task-head">
        <span class="task-title">{{ t.title }}</span>
        <span class="tag" :class="t.classification === '机密' ? 'secret' : 'normal'">{{ t.classification }}</span>
      </div>
      <p v-if="t.detail" class="task-detail">{{ t.detail }}</p>
      <div class="task-meta">
        <span>{{ t.company_name || '未知公司' }}</span>
        <span>· {{ t.manager_name || '负责人' }}</span>
        <span>· 难度 {{ difficultyLabel(t.difficulty) }}</span>
      </div>
      <div class="task-actions">
        <el-button v-if="t.task_company_id !== user.company_id" type="primary" size="small" @click="accept(t)">接取</el-button>
        <el-tag v-else type="info" size="small">本公司任务</el-tag>
      </div>
    </div>
    <p v-if="!tasks.length" class="empty">暂无外包任务</p>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue"
import { getOutsourceTasks, acceptOutsource } from "./api.js"
import { difficultyLabel } from "./format.js"
import { ElMessage } from "element-plus"

const props = defineProps(["user"])
const tasks = ref([])

async function load() {
  try { tasks.value = (await getOutsourceTasks()).tasks || [] } catch (e) { /* 忽略 */ }
}

async function accept(t) {
  const r = await acceptOutsource(t.id, props.user.id)
  if (r.ok) { ElMessage.success("已接取，等待你的 Agent 报价"); await load() }
  else ElMessage.error(r.msg || "接取失败")
}

onMounted(load)
</script>

<style scoped>
.outsource-hall { max-width: 520px; margin: 0 auto; }
.head { margin-bottom: 14px; }
.head h2 { margin: 0 0 4px; }
.sub { margin: 0; font-size: 13px; color: var(--muted); }

.task-card { background: #fff; border: 1px solid var(--line); border-radius: 14px; padding: 14px 16px; margin-bottom: 12px; }
.task-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.task-title { font-size: 15px; font-weight: 600; }
.tag { font-size: 11px; padding: 2px 8px; border-radius: 10px; flex-shrink: 0; }
.tag.secret { background: #fdecec; color: #d6336c; }
.tag.normal { background: #eef2ff; color: var(--brand); }
.task-detail { margin: 8px 0 0; font-size: 13px; color: #4b5158; }
.task-meta { display: flex; gap: 6px; margin-top: 8px; font-size: 12px; color: var(--muted); }
.task-actions { margin-top: 10px; }
.empty { color: var(--muted); text-align: center; padding: 32px 0; }
</style>
