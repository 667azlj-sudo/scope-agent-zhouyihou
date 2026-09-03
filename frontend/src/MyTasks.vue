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

      <div class="list-title">我的任务</div>
      <div v-for="t in tasks" :key="t.id" class="task-card">
        <div class="task-head">
          <span class="task-title">{{ t.title }}</span>
          <span class="tag" :class="t.classification === '机密' ? 'secret' : 'normal'">{{ t.classification }}</span>
        </div>
        <div class="task-meta">
          <span class="meta">难度 · {{ difficultyLabel(t.difficulty) }}</span>
          <span class="meta status" :class="t.status">{{ statusLabel(t.status) }}</span>
        </div>
        <p v-if="t.detail" class="task-detail">{{ t.detail }}</p>

        <template v-if="isSubmittable(t.status)">
          <div class="submit">
            <textarea v-model="drafts[t.id]" rows="2" placeholder="写下你的成果，提交给负责人审核…"></textarea>
            <button class="submit-btn" :disabled="!drafts[t.id]" @click="submit(t)">提交成果</button>
          </div>
        </template>

        <div v-if="t.submission_status === 'approved'" class="feedback ok">
          已通过，绩效价 {{ money(t.submission_price) }}
        </div>
        <div v-else-if="t.submission_status === 'rejected'" class="feedback bad">
          已打回，请修改后重新提交
        </div>
        <div v-else-if="t.submission_status === 'pending'" class="feedback warn">
          已提交，等待负责人审核
        </div>
      </div>

      <p v-if="!tasks.length" class="empty-list">暂时没有派给你的任务</p>
    </template>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from "vue"
import { getAgentByUser, getMyTasks, getSalary, submitWork } from "./api.js"
import { statusLabel, difficultyLabel, money } from "./format.js"
import { ElMessage } from "element-plus"

const props = defineProps(["user"])
const agent = ref(null), tasks = ref([]), salary = ref({ base_salary: 0, exempt: 0 })
const drafts = reactive({})

const totalEarned = computed(() =>
  tasks.value
    .filter(t => t.submission_status === "approved")
    .reduce((s, t) => s + (Number(t.submission_price) || 0), 0)
)

function isSubmittable(s) { return s === "pending" || s === "assigned" || s === "rejected" }

async function load() {
  const a = await getAgentByUser(props.user.id)
  agent.value = a || null
  if (!agent.value) return
  const [t, s] = [await getMyTasks(agent.value.id), await getSalary(props.user.id)]
  tasks.value = t.tasks || []
  salary.value = s
}

async function submit(t) {
  const content = (drafts[t.id] || "").trim()
  if (!content) { ElMessage.warning("请先填写成果内容"); return }
  try {
    await submitWork(t.id, agent.value.id, content)
    ElMessage.success("已提交，等待负责人审核")
    drafts[t.id] = ""
    await load()
  } catch (e) {
    ElMessage.error("提交失败：" + (e.message || "请稍后重试"))
  }
}

onMounted(load)
</script>

<style scoped>
.empty { text-align: center; padding: 48px 0; color: var(--muted); }
.empty-icon { font-size: 40px; margin-bottom: 8px; }
.empty-title { font-size: 16px; font-weight: 600; color: var(--ink); }
.empty-sub { font-size: 13px; margin-top: 4px; }

.income { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 20px; }
.income-item { background: #fff; border: 1px solid var(--line); border-radius: 14px; padding: 14px 10px; text-align: center; }
.income-label { font-size: 12px; color: var(--muted); }
.income-num { margin-top: 6px; font-size: 18px; font-weight: 700; }
.income-num.accent { color: var(--brand); }

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

.submit { margin-top: 12px; }
.submit textarea { width: 100%; border: 1px solid var(--line); border-radius: 10px; padding: 10px; font-family: inherit; font-size: 13px; resize: none; }
.submit-btn { margin-top: 8px; width: 100%; background: var(--brand); color: #fff; border: none; border-radius: 10px; padding: 10px; cursor: pointer; }
.submit-btn:disabled { background: #c7d4f5; cursor: not-allowed; }

.feedback { margin-top: 10px; font-size: 13px; padding: 8px 12px; border-radius: 8px; }
.feedback.ok { background: #e9f7ef; color: #2e9e5b; }
.feedback.bad { background: #fdecec; color: #d6336c; }
.feedback.warn { background: #fff6e6; color: #b7791f; }
.empty-list { text-align: center; color: var(--muted); padding: 24px 0; }
</style>
