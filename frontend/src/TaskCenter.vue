<template>
  <div class="task-center">
    <el-card shadow="never" class="card">
      <h3>新建任务</h3>
      <p class="hint">填写任务内容，系统会自动拆解成子任务，并标注是否需要保密。</p>
      <el-input v-model="title" placeholder="任务名称，例如：开发企业官网" class="mb" />
      <el-input v-model="detail" placeholder="补充任务要求" class="mb" />
      <el-button type="primary" :loading="loading" @click="doSplit">拆解任务</el-button>
    </el-card>

    <el-card shadow="never" class="card">
      <h3>待分级</h3>
      <p class="hint">自动拆解出的子任务，请决定内部处理还是外包。</p>
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

    <el-card shadow="never" class="card">
      <h3>待分发</h3>
      <p class="hint">内部任务，选择一位员工的 Agent 分发过去，由它先报价。</p>
      <div v-for="t in internals" :key="t.id" class="item">
        <div class="item-main">
          <span class="title">{{ t.title }}</span>
        </div>
        <div class="distribute">
          <el-select v-model="distributeTarget[t.id]" placeholder="选员工 Agent" size="small" style="width: 160px">
            <el-option v-for="a in employeeAgents" :key="a.id" :label="a.user_name || a.name" :value="a.id" />
          </el-select>
          <el-button size="small" type="primary" @click="distribute(t)">分发</el-button>
        </div>
      </div>
      <p v-if="!internals.length" class="empty">没有待分发的任务</p>
    </el-card>

    <el-card shadow="never" class="card">
      <h3>待审核报价</h3>
      <p class="hint">员工 Agent 报出的工时与工资，通过后任务才正式派发。</p>
      <div v-for="t in estimates" :key="t.id" class="item estimate">
        <div class="estimate-main">
          <span class="title">{{ t.title }}</span>
          <div class="estimate-line">
            <span>工时 {{ t.estimated_hours }}h</span>
            <span class="wage">报价 ¥{{ t.estimated_wage }}</span>
          </div>
          <p v-if="t.estimate_reason" class="reason">{{ t.estimate_reason }}</p>
        </div>
        <div class="item-actions">
          <el-button size="small" type="success" @click="approveEstimate(t, true)">通过</el-button>
          <el-button size="small" type="danger" plain @click="approveEstimate(t, false)">打回</el-button>
        </div>
      </div>
      <p v-if="!estimates.length" class="empty">没有待审核的报价</p>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from "vue"
import { splitTask, pendingClassify, classifyTask, getAgentByUser, listAgents, internalTasks, estimatedTasks, distributeTask, reviewEstimate } from "./api.js"
import { ElMessage } from "element-plus"

const props = defineProps(["user"])
const title = ref(""), detail = ref(""), pendings = ref([]), loading = ref(false)
const internals = ref([]), estimates = ref([]), agents = ref([])
const distributeTarget = reactive({})
const managerAgentId = ref(null)

const employeeAgents = computed(() => agents.value.filter(a => a.role_type !== "manager"))

async function loadAll() {
  try { pendings.value = (await pendingClassify()).tasks || [] } catch (e) { /* 忽略 */ }
  try { internals.value = (await internalTasks()).tasks || [] } catch (e) { /* 忽略 */ }
  try { estimates.value = (await estimatedTasks()).tasks || [] } catch (e) { /* 忽略 */ }
  try { agents.value = (await listAgents()).agents || [] } catch (e) { /* 忽略 */ }
}

async function ensureManagerAgent() {
  if (managerAgentId.value) return managerAgentId.value
  try { const a = await getAgentByUser(props.user.id); if (a) managerAgentId.value = a.id } catch (e) { /* 忽略 */ }
  return managerAgentId.value || props.user.id
}

async function doSplit() {
  if (!title.value) { ElMessage.warning("请填写任务名称"); return }
  loading.value = true
  try {
    const mid = await ensureManagerAgent()
    await splitTask(title.value, detail.value, mid)
    title.value = ""; detail.value = ""
    await loadAll()
    ElMessage.success("拆解完成，请确认分级")
  } catch (e) {
    ElMessage.error("拆解失败：" + (e.message || "请稍后重试"))
  } finally {
    loading.value = false
  }
}

async function choose(id, c) {
  await classifyTask(id, c)
  await loadAll()
}

async function distribute(t) {
  const aid = distributeTarget[t.id]
  if (!aid) { ElMessage.warning("请先选择员工的 Agent"); return }
  const r = await distributeTask(t.id, aid)
  if (r.ok) { ElMessage.success("已分发，等待员工 Agent 报价"); await loadAll() }
  else ElMessage.error(r.msg || "分发失败")
}

async function approveEstimate(t, ok) {
  const r = await reviewEstimate(t.id, ok)
  ElMessage.success(r.msg || (ok ? "已通过" : "已打回"))
  await loadAll()
}

onMounted(loadAll)
</script>

<style scoped>
.card { margin-bottom: 16px; }
.card h3 { margin: 0 0 6px; font-size: 15px; }
.hint { margin: 0 0 14px; font-size: 12px; color: var(--muted); }
.mb { margin-bottom: 10px; }
.item { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 12px 0; border-bottom: 1px solid var(--line); }
.item:last-child { border-bottom: none; }
.item-main { display: flex; align-items: center; gap: 8px; flex: 1; min-width: 0; }
.item .title { flex: 1; font-size: 14px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.item-actions { display: flex; gap: 6px; flex-shrink: 0; }
.distribute { display: flex; gap: 6px; flex-shrink: 0; align-items: center; }
.estimate { align-items: flex-start; }
.estimate-main { flex: 1; min-width: 0; }
.estimate-line { display: flex; gap: 12px; margin-top: 6px; font-size: 13px; }
.estimate-line .wage { color: var(--brand); font-weight: 600; }
.reason { margin: 6px 0 0; font-size: 12px; color: var(--muted); }
.empty { color: var(--muted); text-align: center; padding: 16px 0; }
</style>
