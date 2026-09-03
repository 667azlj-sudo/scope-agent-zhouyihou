<template>
  <div class="review-salary">
    <el-card class="panel" shadow="never">
      <template #header>
        <div class="panel-head">
          <span class="panel-title">审核提交</span>
          <span class="desc">员工提交 → Agent 自检 → 经理 Agent 跑测试 → 经理核验 → 技术员验证</span>
        </div>
      </template>

      <div v-if="submissions.length">
        <div v-for="s in submissions" :key="s.sid" class="sub-item">
          <div class="sub-head">
            <span class="sub-task">{{ s.task_title }}</span>
            <el-tag size="small" type="info" effect="plain">{{ stageLabel(s.stage) }}</el-tag>
          </div>
          <div class="sub-from">{{ s.submitter_name || s.agent_name }}{{ s.submitter_position ? " · " + s.submitter_position : "" }}</div>
          <p class="sub-content">{{ s.content }}</p>
          <div v-if="s.images && s.images.length" class="sub-imgs">
            <img v-for="u in s.images" :key="u" :src="u" class="sub-img" />
          </div>

          <!-- 阶段① 员工 Agent 自检 -->
          <div v-if="s.stage === 'submitted'" class="sub-actions">
            <el-button size="small" type="primary" @click="doAgentCheck(s)">员工 Agent 检查</el-button>
          </div>

          <!-- 阶段② 经理 Agent 跑测试 -->
          <div v-else-if="s.stage === 'agent_checked'" class="sub-actions">
            <el-button size="small" type="primary" @click="doManagerTest(s)">经理 Agent 跑测试</el-button>
          </div>

          <!-- 阶段③ 经理核验 -->
          <div v-else-if="s.stage === 'manager_tested'" class="sub-actions">
            <el-input-number v-model="customPriceMap[s.sid]" :min="0" :precision="2" :step="100" controls-position="right" size="small" placeholder="改价" style="width: 110px" />
            <div class="sub-btns">
              <el-button size="small" type="success" @click="doManagerVerify(s, true)">核验通过</el-button>
              <el-button size="small" type="danger" plain @click="doManagerVerify(s, false)">打回</el-button>
            </div>
          </div>

          <!-- 阶段④ 指定技术员 + 技术员验证 -->
          <div v-else-if="s.stage === 'manager_verified'" class="sub-actions tech">
            <el-select v-model="techMap[s.sid]" placeholder="选技术员" size="small" style="width: 150px">
              <el-option v-for="u in allUsers" :key="u.id" :label="u.name + (u.position ? ' · ' + u.position : '')" :value="u.id" />
            </el-select>
            <el-button size="small" @click="doDesignate(s)">指定</el-button>
            <div class="sub-btns">
              <el-button size="small" type="success" @click="doTechVerify(s, true)">验证通过</el-button>
              <el-button size="small" type="danger" plain @click="doTechVerify(s, false)">打回</el-button>
            </div>
          </div>

          <div v-if="s.tech_reviewer_name" class="tech-note">已指定技术员：{{ s.tech_reviewer_name }}</div>
        </div>
      </div>
      <p v-else class="empty">没有待审核的提交</p>
    </el-card>

    <el-card class="panel" shadow="never">
      <template #header>
        <div class="panel-head">
          <span class="panel-title">结算打款</span>
          <span class="desc">待打款 {{ money(payoutStats.pending_amount) }} · 已打款 {{ money(payoutStats.paid_amount) }}</span>
        </div>
      </template>

      <div class="pay-mode">
        <span class="pm-label">工资发放方式</span>
        <el-radio-group v-model="payMode" size="small" @change="savePayMode">
          <el-radio-button value="monthly">每月固定时间一起发</el-radio-button>
          <el-radio-button value="on_completion">项目完成后发</el-radio-button>
        </el-radio-group>
      </div>

      <div v-if="payMode === 'monthly'" class="pay-all-row">
        <el-button type="primary" size="small" @click="doPayAll">发放本月全部工资</el-button>
      </div>

      <div v-if="payouts.length">
        <div v-for="p in payouts" :key="p.id" class="sub-item">
          <div class="sub-head">
            <span class="sub-task">{{ p.user_name || ("员工 #" + p.user_id) }}</span>
            <span class="payout-amount" :class="p.status">{{ money(p.amount) }}</span>
          </div>
          <div class="payout-meta">
            <span>{{ p.task_title || "任务" }}</span>
            <span>{{ p.status === "paid" ? "已打款" : "待打款" }}</span>
          </div>
          <div class="sub-actions">
            <el-button v-if="p.status === 'pending'" size="small" type="primary" @click="pay(p)">打款</el-button>
            <el-tag v-else type="success" effect="plain">已到账</el-tag>
          </div>
        </div>
      </div>
      <p v-else class="empty">还没有结算记录</p>
    </el-card>

    <el-card class="panel" shadow="never">
      <template #header>
        <div class="panel-head">
          <span class="panel-title">设置工资</span>
          <span class="desc">为成员设置基础工资与豁免状态</span>
        </div>
      </template>

      <el-form :model="salaryForm" label-width="80px" @submit.prevent>
        <el-form-item label="成员编号">
          <el-input v-model="salaryForm.uid" placeholder="输入成员的编号" clearable />
        </el-form-item>
        <el-form-item label="基础工资">
          <el-input-number v-model="salaryForm.baseSalary" :min="0" :precision="2" :step="100" controls-position="right" placeholder="每月基础工资" style="width: 100%" />
        </el-form-item>
        <el-form-item label="豁免绩效">
          <el-switch v-model="salaryForm.exempt" active-text="是" inactive-text="否" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="salaryLoading" @click="submitSalary">保存</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted } from "vue"
import { ElMessage } from "element-plus"
import { setSalary, getPendingSubmissions, getPayouts, payPayout, payAllPayouts, getPayMode, setPayMode, getUsers, agentCheck, managerTest, managerVerify, designateTech, techVerify } from "./api.js"
import { money, stageLabel } from "./format.js"

const props = defineProps(["user"])
const submissions = ref([])
const customPriceMap = reactive({})
const techMap = reactive({})
const allUsers = ref([])

const payouts = ref([])
const payoutStats = ref({ pending_amount: 0, paid_amount: 0 })
const payMode = ref("on_completion")

const salaryForm = reactive({ uid: "", baseSalary: undefined, exempt: false })
const salaryLoading = ref(false)

async function load() {
  try {
    const r = await getPendingSubmissions()
    submissions.value = r.submissions || []
    submissions.value.forEach(s => { customPriceMap[s.sid] = undefined })
  } catch (e) { /* 忽略 */ }
  loadPayouts()
  try { allUsers.value = (await getUsers()).users || [] } catch (e) { /* 忽略 */ }
  if (props.user.company_id) {
    try { payMode.value = (await getPayMode(props.user.company_id)).pay_mode || "on_completion" } catch (e) { /* 忽略 */ }
  }
}

async function loadPayouts() {
  try {
    const r = await getPayouts()
    payouts.value = r.payouts || []
    payoutStats.value = r.stats || { pending_amount: 0, paid_amount: 0 }
  } catch (e) { /* 忽略 */ }
}

async function pay(p) {
  try {
    const res = await payPayout(p.id)
    ElMessage.success(res.msg || "已打款")
    await loadPayouts()
  } catch (e) {
    ElMessage.error("打款失败：" + (e.message || "请稍后重试"))
  }
}

async function doPayAll() {
  try {
    const res = await payAllPayouts()
    ElMessage.success(res.msg || "已发放")
    await loadPayouts()
  } catch (e) {
    ElMessage.error("发放失败：" + (e.message || "请稍后重试"))
  }
}

async function savePayMode(v) {
  try {
    await setPayMode(props.user.company_id, v)
    ElMessage.success("已保存发放方式")
  } catch (e) {
    ElMessage.error("保存失败：" + (e.message || "请稍后重试"))
  }
}

async function doAgentCheck(s) {
  const r = await agentCheck(s.sid)
  ElMessage.success(r.pass ? "自检通过" : ("自检打回：" + (r.reason || "")))
  await load()
}

async function doManagerTest(s) {
  const r = await managerTest(s.sid)
  ElMessage.success(r.pass ? "跑测试通过" : ("跑测试打回：" + (r.reason || "")))
  await load()
}

async function doManagerVerify(s, approve) {
  const r = await managerVerify(s.sid, approve, customPriceMap[s.sid])
  ElMessage.success(r.msg || (approve ? "已核验" : "已打回"))
  await load()
}

async function doDesignate(s) {
  if (!techMap[s.sid]) { ElMessage.warning("请先选择技术员"); return }
  await designateTech(s.sid, techMap[s.sid])
  ElMessage.success("已指定技术员")
  await load()
}

async function doTechVerify(s, approve) {
  const uid = s.tech_reviewer || props.user.id
  const r = await techVerify(s.sid, uid, approve)
  ElMessage.success(r.msg || (approve ? "验证通过" : "已打回"))
  await load()
}

async function submitSalary() {
  if (!salaryForm.uid) { ElMessage.warning("请输入成员编号"); return }
  if (salaryForm.baseSalary == null) { ElMessage.warning("请输入基础工资"); return }
  salaryLoading.value = true
  try {
    await setSalary(salaryForm.uid, salaryForm.baseSalary, salaryForm.exempt)
    ElMessage.success("已保存")
    salaryForm.uid = ""; salaryForm.baseSalary = undefined; salaryForm.exempt = false
  } catch (e) {
    ElMessage.error("保存失败：" + (e.message || "请稍后重试"))
  } finally {
    salaryLoading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.review-salary { max-width: 520px; margin: 0 auto; }
.panel { margin-bottom: 16px; border-radius: 14px; }
.panel-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.panel-title { font-weight: 600; }
.panel-head .desc { font-size: 12px; color: var(--muted); }

.sub-item { padding: 12px 0; border-bottom: 1px solid var(--line); }
.sub-item:last-child { border-bottom: none; }
.sub-head { display: flex; justify-content: space-between; align-items: center; gap: 10px; }
.sub-task { font-size: 14px; font-weight: 600; }
.sub-from { font-size: 12px; color: var(--muted); margin-top: 2px; }
.payout-amount { font-size: 16px; font-weight: 700; color: var(--brand); }
.payout-amount.paid { color: #2e9e5b; }
.payout-meta { display: flex; justify-content: space-between; margin: 6px 0; font-size: 12px; color: var(--muted); }
.sub-content { margin: 8px 0; font-size: 13px; color: #4b5158; white-space: pre-wrap; }
.sub-imgs { display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0; }
.sub-img { width: 72px; height: 72px; object-fit: cover; border-radius: 8px; border: 1px solid var(--line); }
.sub-actions { display: flex; justify-content: flex-end; align-items: center; gap: 8px; margin-top: 8px; }
.sub-actions.tech { flex-wrap: wrap; }
.sub-btns { display: flex; gap: 8px; }
.tech-note { margin-top: 6px; font-size: 12px; color: var(--brand); }
.pay-mode { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.pm-label { font-size: 13px; color: var(--muted); }
.pay-all-row { margin-bottom: 10px; }
.empty { color: var(--muted); text-align: center; padding: 24px 0; }
</style>
