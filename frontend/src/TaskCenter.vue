<template>
  <div class="task-center">
    <el-card shadow="never" class="split-card">
      <h3>新建任务</h3>
      <p class="hint">填写任务内容，系统会自动拆解成子任务，并标注是否需要保密。</p>
      <el-input v-model="title" placeholder="任务名称，例如：开发企业官网" class="mb" />
      <el-input v-model="detail" placeholder="补充任务要求" class="mb" />
      <el-button type="primary" :loading="loading" @click="doSplit">拆解任务</el-button>
    </el-card>

    <el-card shadow="never" class="pending-card">
      <h3>待分级</h3>
      <p class="hint">以下是自动拆解出的子任务，请决定在内部处理，还是外包。</p>
      <div v-for="t in pendings" :key="t.id" class="item">
        <div class="item-main">
          <span class="title">{{ t.title }}</span>
          <el-tag :type="t.classification === '机密' ? 'danger' : 'info'">{{ t.classification }}</el-tag>
        </div>
        <div class="item-actions">
          <el-button size="small" type="danger" plain @click="choose(t.id, 'internal')">内部处理</el-button>
          <el-button size="small" type="primary" plain @click="choose(t.id, 'outsource')">外包</el-button>
        </div>
      </div>
      <p v-if="!pendings.length" class="empty">没有待分级的任务</p>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue"
import { splitTask, pendingClassify, classifyTask, getAgentByUser } from "./api.js"
import { ElMessage } from "element-plus"

const props = defineProps(["user"])
const title = ref(""), detail = ref(""), pendings = ref([]), loading = ref(false)
const managerAgentId = ref(null)

async function load() {
  pendings.value = (await pendingClassify()).tasks || []
}

async function ensureAgent() {
  if (managerAgentId.value) return managerAgentId.value
  try {
    const a = await getAgentByUser(props.user.id)
    if (a) managerAgentId.value = a.id
  } catch (e) { /* 忽略 */ }
  return managerAgentId.value || props.user.id
}

async function doSplit() {
  if (!title.value) { ElMessage.warning("请填写任务名称"); return }
  loading.value = true
  try {
    const mid = await ensureAgent()
    await splitTask(title.value, detail.value, mid)
    title.value = ""; detail.value = ""
    await load()
    ElMessage.success("拆解完成，请在下方确认分级")
  } catch (e) {
    ElMessage.error("拆解失败：" + (e.message || "请稍后重试"))
  } finally {
    loading.value = false
  }
}

async function choose(id, c) {
  await classifyTask(id, c)
  await load()
}

onMounted(load)
</script>

<style scoped>
.split-card, .pending-card { margin-bottom: 16px; }
.split-card h3, .pending-card h3 { margin: 0 0 6px; font-size: 15px; }
.hint { margin: 0 0 14px; font-size: 12px; color: var(--muted); }
.mb { margin-bottom: 10px; }
.item { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 12px 0; border-bottom: 1px solid var(--line); }
.item-main { display: flex; align-items: center; gap: 8px; flex: 1; min-width: 0; }
.item .title { flex: 1; font-size: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.item-actions { display: flex; gap: 6px; flex-shrink: 0; }
.empty { color: var(--muted); text-align: center; padding: 16px 0; }
</style>
