<template>
  <div class="my-tasks">
    <div v-if="!agent" class="empty">
      <div class="empty-icon">🤖</div>
      <div class="empty-title">还没有绑定 Agent</div>
      <div class="empty-sub">请联系负责人为你分配一个专属 Agent</div>
    </div>

    <template v-else>
      <section class="income">
        <div class="income-item">
          <div class="income-label">基础工资</div>
          <div class="income-num">{{ money(salary.base_salary) }}</div>
        </div>
        <div class="income-item">
          <div class="income-label">已结算绩效</div>
          <div class="income-num accent">{{ money(totalEarned) }}</div>
        </div>
        <div class="income-item">
          <div class="income-label">豁免状态</div>
          <div class="income-num">{{ salary.exempt ? "豁免" : "正常" }}</div>
        </div>
      </section>

      <el-collapse v-model="recordsOpen" class="records">
        <el-collapse-item title="我的本地记录（Agent 报价依据）" name="rec">
          <p class="records-hint">写清你的技能、经验、历史产出，Agent 会据此为你报价。</p>
          <el-input v-model="records" type="textarea" :rows="4" placeholder="例如：5 年后端经验，擅长 Python/FastAPI，日均产出 3 个接口…" />
          <el-button class="records-save" type="primary" size="small" :loading="savingRecords" @click="saveMyRecords">保存</el-button>
        </el-collapse-item>
        <el-collapse-item title="工作记录（Agent 判断任务是否适合你）" name="work">
          <p class="records-hint">导入你的工作记录，Agent 会据此判断任务适配度。</p>
          <div class="work-add">
            <el-input v-model="newWorkRecord" type="textarea" :rows="2" placeholder="例如：本周完成订单系统重构，熟练使用 Python 与 Redis" />
            <el-button type="primary" size="small" @click="addMyWorkRecord">添加</el-button>
          </div>
          <div v-for="w in workRecords" :key="w.id" class="work-item">
            <span class="work-text">{{ w.content }}</span>
            <span class="work-del" @click="removeWorkRecord(w.id)">×</span>
          </div>
        </el-collapse-item>
      </el-collapse>

      <div class="list-title">我的任务</div>

      <div v-for="t in tasks" :key="t.id" class="task-card">
        <div class="task-head">
          <span class="task-title">{{ t.title }}</span>
          <span class="tag" :class="t.classification === '机密' ? 'secret' : 'normal'">{{ t.classification }}</span>
        </div>
        <div class="task-meta">
          <span class="meta">难度 · {{ difficultyLabel(t.difficulty) }}</span>
          <span class="meta status">{{ statusLabel(t.status) }}</span>
        </div>
        <p v-if="t.detail" class="task-detail">{{ t.detail }}</p>

        <!-- 待报价：员工 agent 审核任务并报价 -->
        <div v-if="t.status === 'distributed'" class="action">
          <p class="action-hint">负责人已分发此任务，先让 Agent 结合你的本地记录报价。</p>
          <el-button type="primary" size="small" :loading="estimating[t.id]" @click="doEstimate(t)">让 Agent 报价</el-button>
        </div>

        <!-- 报价已提交，等待经理审核 -->
        <div v-else-if="t.status === 'estimated'" class="feedback warn">
          <div>已报价：工时 {{ t.estimated_hours }}h · ¥{{ t.estimated_wage }}</div>
          <div v-if="t.suitability" class="suit">适配度：{{ t.suitability }}{{ t.suitability_reason ? ' · ' + t.suitability_reason : '' }}</div>
          <div v-if="t.conditions" class="suit">任务条件：{{ t.conditions }}</div>
          <div v-if="t.needs_conditions" class="suit need">条件库暂无此任务条件，已通知负责人补充</div>
        </div>

        <!-- 进行中 / 已打回：提交成果 -->
        <template v-else-if="t.status === 'assigned' || t.status === 'rejected'">
          <div v-if="t.status === 'rejected'" class="feedback bad">负责人已打回，请修改后重新提交</div>
          <div class="submit">
            <textarea v-model="drafts[t.id]" rows="2" placeholder="写下你的成果，提交给负责人审核…"></textarea>
            <div v-if="images[t.id] && images[t.id].length" class="imgs">
              <div v-for="(u, i) in images[t.id]" :key="u" class="img-item">
                <img :src="u" />
                <span class="img-del" @click="removeImg(t.id, i)">×</span>
              </div>
            </div>
            <div class="submit-row">
              <button class="photo-btn" @click="pickImage(t)">📷 传照片证明</button>
              <button class="submit-btn" :disabled="!drafts[t.id]" @click="submit(t)">提交成果</button>
            </div>
          </div>
        </template>

        <!-- 已提交 -->
        <div v-else-if="t.status === 'submitted'" class="feedback warn">已提交，等待负责人审核</div>

        <!-- 已完成 -->
        <div v-else-if="t.status === 'done'" class="feedback ok">
          已完成，绩效价 {{ money(t.submission_price || t.agreed_wage) }}
        </div>
      </div>

      <p v-if="!tasks.length" class="empty-list">暂时没有派给你的任务</p>
    </template>

    <input ref="imgInput" type="file" accept="image/*" multiple hidden @change="onPickImage" />
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from "vue"
import { getAgentByUser, getMyTasks, getSalary, submitWork, estimateTask, getRecords, saveRecords, uploadSubmissionImage, getWorkRecords, addWorkRecord, deleteWorkRecord } from "./api.js"
import { statusLabel, difficultyLabel, money } from "./format.js"
import { ElMessage } from "element-plus"

const props = defineProps(["user"])
const agent = ref(null), tasks = ref([]), salary = ref({ base_salary: 0, exempt: 0 })
const drafts = reactive({}), estimating = reactive({}), images = reactive({})
const records = ref(""), recordsOpen = ref([]), savingRecords = ref(false)
const workRecords = ref([]), newWorkRecord = ref("")
const imgInput = ref(null), currentUploadTaskId = ref(null)

const totalEarned = computed(() =>
  tasks.value
    .filter(t => t.status === "done")
    .reduce((s, t) => s + (Number(t.submission_price) || 0), 0)
)

async function load() {
  const a = await getAgentByUser(props.user.id)
  agent.value = a || null
  if (!agent.value) return
  const [t, s, rec] = [await getMyTasks(agent.value.id), await getSalary(props.user.id), await getRecords(props.user.id)]
  tasks.value = t.tasks || []
  salary.value = s
  records.value = rec.content || ""
  await loadWorkRecords()
}

async function loadWorkRecords() {
  try { workRecords.value = (await getWorkRecords(props.user.id)).records || [] } catch (e) { /* 忽略 */ }
}

async function addMyWorkRecord() {
  const c = newWorkRecord.value.trim()
  if (!c) { ElMessage.warning("请填写工作记录内容"); return }
  try {
    await addWorkRecord(props.user.id, c)
    newWorkRecord.value = ""
    await loadWorkRecords()
    ElMessage.success("已添加工作记录")
  } catch (e) {
    ElMessage.error("添加失败：" + (e.message || "请重试"))
  }
}

async function removeWorkRecord(rid) {
  await deleteWorkRecord(rid)
  await loadWorkRecords()
}

async function saveMyRecords() {
  savingRecords.value = true
  try {
    await saveRecords(props.user.id, records.value)
    ElMessage.success("本地记录已保存")
  } catch (e) {
    ElMessage.error("保存失败：" + (e.message || "请稍后重试"))
  } finally {
    savingRecords.value = false
  }
}

async function doEstimate(t) {
  estimating[t.id] = true
  try {
    const r = await estimateTask(t.id, agent.value.id)
    ElMessage.success(`报价完成：工时 ${r.hours}h · ¥${r.wage}`)
    await load()
  } catch (e) {
    ElMessage.error("报价失败：" + (e.message || "请稍后重试"))
  } finally {
    estimating[t.id] = false
  }
}

async function submit(t) {
  const content = (drafts[t.id] || "").trim()
  if (!content) { ElMessage.warning("请先填写成果内容"); return }
  try {
    await submitWork(t.id, agent.value.id, content, images[t.id] || [])
    ElMessage.success("已提交，等待负责人审核")
    drafts[t.id] = ""
    images[t.id] = []
    await load()
  } catch (e) {
    ElMessage.error("提交失败：" + (e.message || "请稍后重试"))
  }
}

function pickImage(t) {
  currentUploadTaskId.value = t.id
  if (imgInput.value) imgInput.value.click()
}

async function onPickImage(e) {
  const files = Array.from(e.target.files || [])
  if (!files.length || !currentUploadTaskId.value) { e.target.value = ""; return }
  const tid = currentUploadTaskId.value
  if (!images[tid]) images[tid] = []
  for (const f of files) {
    try {
      const r = await uploadSubmissionImage(f)
      if (r.url) images[tid].push(r.url)
    } catch (err) {
      ElMessage.error("照片上传失败：" + (err.message || "请重试"))
    }
  }
  e.target.value = ""
}

function removeImg(tid, i) {
  if (images[tid]) images[tid].splice(i, 1)
}

onMounted(load)
</script>

<style scoped>
.empty { text-align: center; padding: 48px 0; color: var(--muted); }
.empty-icon { font-size: 40px; margin-bottom: 8px; }
.empty-title { font-size: 16px; font-weight: 600; color: var(--ink); }
.empty-sub { font-size: 13px; margin-top: 4px; }

.income { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 16px; }
.income-item { background: #fff; border: 1px solid var(--line); border-radius: 14px; padding: 14px 10px; text-align: center; }
.income-label { font-size: 12px; color: var(--muted); }
.income-num { margin-top: 6px; font-size: 18px; font-weight: 700; }
.income-num.accent { color: var(--brand); }

.records { margin-bottom: 16px; background: #fff; border: 1px solid var(--line); border-radius: 14px; }
.records-hint { font-size: 12px; color: var(--muted); margin: 0 0 8px; }
.records-save { margin-top: 8px; }
.work-add { display: flex; gap: 8px; align-items: flex-start; }
.work-add .el-textarea { flex: 1; }
.work-item { display: flex; justify-content: space-between; align-items: center; gap: 8px; padding: 8px 0; border-bottom: 1px solid var(--line); font-size: 13px; }
.work-item:last-child { border-bottom: none; }
.work-text { flex: 1; color: #4b5158; }
.work-del { color: var(--muted); cursor: pointer; font-size: 16px; padding: 0 4px; }
.suit { font-size: 12px; margin-top: 4px; color: #6b7280; }
.suit.need { color: #b7791f; }

.list-title { font-size: 14px; font-weight: 600; margin-bottom: 12px; }
.task-card { background: #fff; border: 1px solid var(--line); border-radius: 14px; padding: 14px 16px; margin-bottom: 12px; }
.task-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.task-title { font-size: 15px; font-weight: 600; }
.tag { font-size: 11px; padding: 2px 8px; border-radius: 10px; flex-shrink: 0; }
.tag.secret { background: #fdecec; color: #d6336c; }
.tag.normal { background: #eef2ff; color: var(--brand); }
.task-meta { display: flex; gap: 10px; margin-top: 8px; }
.meta { font-size: 12px; color: var(--muted); }
.task-detail { margin: 8px 0 0; font-size: 13px; color: #4b5158; }

.action { margin-top: 12px; }
.action-hint { font-size: 12px; color: var(--muted); margin: 0 0 8px; }

.submit { margin-top: 12px; }
.submit textarea { width: 100%; border: 1px solid var(--line); border-radius: 10px; padding: 10px; font-family: inherit; font-size: 13px; resize: none; }
.submit-btn { width: 100%; background: var(--brand); color: #fff; border: none; border-radius: 10px; padding: 10px; cursor: pointer; }
.submit-btn:disabled { background: #c7d4f5; cursor: not-allowed; }
.submit-row { display: flex; gap: 8px; margin-top: 8px; }
.submit-row .submit-btn { width: auto; flex: 1; margin-top: 0; }
.photo-btn { background: #fff; border: 1px solid var(--line); border-radius: 10px; padding: 10px 12px; cursor: pointer; color: var(--ink); }
.imgs { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.img-item { position: relative; }
.img-item img { width: 72px; height: 72px; object-fit: cover; border-radius: 8px; border: 1px solid var(--line); }
.img-del { position: absolute; top: -6px; right: -6px; width: 18px; height: 18px; background: rgba(0,0,0,.6); color: #fff; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; cursor: pointer; }

.feedback { margin-top: 10px; font-size: 13px; padding: 8px 12px; border-radius: 8px; }
.feedback.ok { background: #e9f7ef; color: #2e9e5b; }
.feedback.bad { background: #fdecec; color: #d6336c; }
.feedback.warn { background: #fff6e6; color: #b7791f; }
.empty-list { text-align: center; color: var(--muted); padding: 24px 0; }
</style>
