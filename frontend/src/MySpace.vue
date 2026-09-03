<template>
  <div class="my-space">
    <section class="profile">
      <div class="avatar">{{ initial }}</div>
      <div class="info">
        <div class="name">{{ user.name }}</div>
        <div class="role">{{ roleLabel(user.role) }}</div>
      </div>
      <div class="uid">编号 {{ user.id }}</div>
    </section>

    <section class="card">
      <div class="card-title">我的工资</div>
      <div class="salary-row">
        <div>
          <div class="slabel">基础工资</div>
          <div class="snum">{{ money(salary.base_salary) }}</div>
        </div>
        <div>
          <div class="slabel">已结算绩效</div>
          <div class="snum accent">{{ money(totalEarned) }}</div>
        </div>
        <div>
          <div class="slabel">豁免状态</div>
          <div class="snum">{{ salary.exempt ? "豁免" : "正常" }}</div>
        </div>
      </div>
      <p v-if="!salary.base_salary" class="hint">负责人尚未为你设置基础工资</p>
    </section>

    <section class="card">
      <div class="card-title">我的小组</div>
      <div class="line"><span>绑定 Agent</span><span>{{ agentName }}</span></div>
      <div class="line"><span>进行中任务</span><span>{{ activeTasks }} 项</span></div>
    </section>

    <section class="card">
      <div class="card-title">到账记录</div>
      <div v-if="payouts.length">
        <div v-for="p in payouts" :key="p.id" class="line">
          <span>{{ p.task_title || "任务" }}</span>
          <span class="paid" :class="p.status">{{ p.status === "paid" ? money(p.amount) : "待打款" }}</span>
        </div>
      </div>
      <p v-else class="hint">还没有结算记录，完成并审核通过的任务会在这里到账</p>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue"
import { getAgentByUser, getMyTasks, getSalary, getUserPayouts } from "./api.js"
import { roleLabel, money } from "./format.js"

const props = defineProps(["user"])
const salary = ref({ base_salary: 0, exempt: 0 })
const agentName = ref("未绑定")
const tasks = ref([])
const payouts = ref([])

const initial = computed(() => (props.user.name || "?")[0])
const totalEarned = computed(() =>
  tasks.value
    .filter(t => t.submission_status === "approved")
    .reduce((s, t) => s + (Number(t.submission_price) || 0), 0)
)
const activeTasks = computed(() => tasks.value.filter(t => t.status !== "done").length)

onMounted(async () => {
  try { salary.value = await getSalary(props.user.id) } catch (e) { /* 忽略 */ }
  try {
    const a = await getAgentByUser(props.user.id)
    if (a) {
      agentName.value = a.name
      const t = await getMyTasks(a.id)
      tasks.value = t.tasks || []
    }
  } catch (e) { /* 忽略 */ }
  try { payouts.value = (await getUserPayouts(props.user.id)).payouts || [] } catch (e) { /* 忽略 */ }
})
</script>

<style scoped>
.my-space { max-width: 520px; margin: 0 auto; }
.profile { display: flex; align-items: center; gap: 14px; padding: 6px 2px 18px; }
.avatar { width: 56px; height: 56px; border-radius: 16px; background: var(--brand-soft); color: var(--brand); display: flex; align-items: center; justify-content: center; font-size: 24px; font-weight: 700; flex-shrink: 0; }
.info { flex: 1; }
.name { font-size: 19px; font-weight: 700; }
.role { margin-top: 2px; font-size: 12px; color: var(--muted); }
.uid { font-size: 12px; color: var(--muted); }

.card { background: #fff; border: 1px solid var(--line); border-radius: 14px; padding: 16px; margin-bottom: 16px; }
.card-title { font-size: 14px; font-weight: 600; margin-bottom: 12px; }
.salary-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.slabel { font-size: 12px; color: var(--muted); }
.snum { margin-top: 4px; font-size: 18px; font-weight: 700; }
.snum.accent { color: var(--brand); }
.hint { margin-top: 12px; font-size: 12px; color: var(--muted); }

.line { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid var(--line); font-size: 14px; }
.line:last-child { border-bottom: none; }
.line span:last-child { color: var(--ink); }
.paid { font-weight: 600; color: var(--brand); }
.paid.paid { color: #2e9e5b; }
.paid.pending { color: #b7791f; }
</style>
